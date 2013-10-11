#!/usr/bin/env python2
from __future__ import division, print_function
__author__ = 'Rich Li'
__version__ = 1.0
""" Monitors mail folders for changes using IDLE and then runs offlineimap

The mail configuration (login details, folders) are specified with an
ini-style config.

TODO: I currently use logging from stdlib. Can I also use systemd's logging
ability?

"""

# stdlib imports
import sys
import time
import subprocess
import argparse
import threading
import ConfigParser
import logging

# other imports
from imapclient import IMAPClient # python2-imapclient on AUR

class idle_checker(threading.Thread):
    """ This checks an IMAP folder using IDLE 

    As many instances of this class (threads) need to be created as IMAP
    folders to be checked
    
    """

    stop_it = False
    def __init__(self, trigger_event, mail_acct, mail_user, mail_pass, mail_server, mail_folder):
        """ Initializes the thread

        trigger_event: an event to notify that a mailcheck is needed
        mail_acct: the offlineimap account name
        mail_user: IMAP username 
        mail_pass: IMAP password
        mail_server: IMAP hostname (SSL is assumed yes)
        mail_folder: IMAP foldername

        """
        super(idle_checker, self).__init__()

        self.trigger_event = trigger_event
        self.mail_acct = mail_acct
        self.mail_user = mail_user
        self.mail_pass = mail_pass
        self.mail_server = mail_server
        self.mail_folder = mail_folder

        server = IMAPClient(mail_server, use_uid=True, ssl=True)
        #server.debug = True
        server.login(mail_user, mail_pass)

        self.server = server
        #self.timeout = 60*29 # 29 minutes
        self.timeout = 10 # DEBUG?

        self.last_sync = time.time()
        self.last_print = time.time()

    def run(self):
        server = self.server
        select_info = server.select_folder(self.mail_folder)
        while True:
            #logging.debug("{}: idling".format(self.name))
            # Display status periodically
            if (time.time() - self.last_print) / 60 >= 5 :
                logging.info("{}: idling at {}, {:0.1f} min since last sync".format(
                    self.name, time.strftime("%d %b %I:%M:%S"), (time.time() - self.last_sync)/60))
                self.last_print = time.time()

            server.idle()
            idle_response = server.idle_check(timeout=self.timeout)
            #print(idle_response)
            idle_done = server.idle_done()
            if len(idle_done[1:]) > 0 and len(idle_done[1]) > 0:
                idle_response.extend([i[0] for i in idle_done[1:]])
                #print("idle_response extended", idle_done, idle_response)
            #idle_response.append(server.noop())

            # Check if we need to exit
            if idle_checker.stop_it:
                logging.info("{}: Terminating thread".format(self.name))
                break

            # Check idle_response. Don't need to trigger offlineimap
            # in all cases.
            for resp in idle_response:
                #print(self.name, idle_response, resp)
                #if isinstance(resp[0], (str,unicode)) and resp[0].upper().startswith("IDLE"):
                #    continue
                #if len(resp) < 2:
                #    continue
                if len(resp) < 2:
                    logging.error("{}: resp is {}".format(self.name, resp))

                # Trigger immediately for new mail
                # For mail changes (flags, deletion), wait a little for things
                # to settle
                if resp[1] in (u'RECENT', u'EXISTS'):
                    # recent: new mail
                    # exists: number of messages in mailbox
                    # NB: it seems dovecot uses "recent" and gmail uses "exists"
                    logging.info("{}: Triggering due to {}".format(self.name, resp[1]))
                    idle_actor.accts.append(self.mail_acct)
                    self.trigger_event.set()
                    self.trigger_event.clear()
                    self.last_sync = time.time()
                elif resp[1] in (u'FETCH', u'EXPUNGE'):
                    # fetch: something about the message changed (flags, etc)
                    # expunge: message deleted (expunged) from mailbox
                    # NB: while dovecot will notify on flag changes using "fetch", gmail does not
                    logging.info("{}: Triggering (delayed) due to {}".format(self.name, resp[1]))
                    time.sleep(10)
                    idle_actor.accts.append(self.mail_acct)
                    self.trigger_event.set()
                    self.trigger_event.clear()
                    self.last_sync = time.time()
                elif resp[1] in (u'Still here'):
                    # These responses don't need an offlineimap sync
                    #logging.info("{}: No action due to {}".format(self.name, resp[1]))
                    pass
                else:
                    # TODO: Any other cases happen?
                    logging.warning("{} UNKNOWN idle response: {}".format(self.name,resp))

            # Trigger sync anyway if it's been long enough
            if (time.time() - self.last_sync) > 60 * 60:
                logging.info("{}: Triggering due to timeout".format(self.name))
                idle_actor.accts.append(self.mail_acct)
                self.trigger_event.set()
                self.trigger_event.clear()
                self.last_sync = time.time()

        server.logout()

class idle_actor(threading.Thread):
    """ This triggers offlineimap 
    
    Only one instance of this class (thread) is needed
    
    """

    stop_it = False
    accts = []
    def __init__(self, trigger_event):
        super(idle_actor, self).__init__()
        self.trigger_event = trigger_event

    def run(self):
        while True:
            self.trigger_event.wait()
            logging.info("{}: triggered".format(self.name))

            # Check if we need to exit
            if idle_actor.stop_it:
                logging.info("{}: Terminating thread".format(self.name))
                break

            # Run offlineimap for the accounts
            while len(idle_actor.accts) > 0:
                acct = idle_actor.accts.pop()
                cmd = ["/usr/bin/offlineimap", "-o", "-a", acct, "-k", "mbnames:enabled=no"]
                logging.info("Calling {}".format(cmd))
                #subprocess.Popen(cmd)
                cmd_out = subprocess.check_output(cmd)
                print(cmd_out)

def main():
    """ IDLE on certain IMAP folders 

    Each IDLE command is only for one folder, so I need to spawn several IMAP
    sessions. Each session is in its own thread. Because the code is IO-bound
    instead of CPU-bound the limitations of the GIL don't concern me here.
    
    """
    # Parse args
    parser = argparse.ArgumentParser(description="IDLE on certain IMAP folders")
    parser.add_argument('--version', action='version', 
            version='%(prog)s version {}'.format(__version__))
    args = parser.parse_args()

    logging.basicConfig(
            level=logging.INFO,
            format='%(levelname)s: %(message)s',
            #format='%(asctime)s %(levelname)s: %(message)s',
            #filename='/home/earl/.local/bin/idle_sync.log',
            )

    # Read in account info
    cfg = ConfigParser.SafeConfigParser()
    cfg.read('idle_mail.ini')

    # Create the consumer thread and its event it watches
    trigger_event = threading.Event()
    trigger_thread = idle_actor(trigger_event)
    trigger_thread.name = "idle-actor"
    trigger_thread.start()

    # Create the producer threads
    idle_threads = []
    for acct in cfg.sections():
        mail_user = cfg.get(acct, "user")
        mail_pass = cfg.get(acct, "pass")
        mail_server = cfg.get(acct, "server")
        mail_folders = cfg.get(acct, "folders")

        for folder in mail_folders.split(","):
            thread_name='{}_{}'.format(acct, folder.strip())
            logging.info("Spawning {}".format(thread_name))
            mail_idle = idle_checker(trigger_event, acct, mail_user,
                    mail_pass, mail_server, folder.strip())
            mail_idle.name = thread_name
            idle_threads.append(mail_idle)
            mail_idle.start()

    # Run threads, but watch for SIGINT and terminate gracefully
    try:
        while True:
            for thread in idle_threads:
                if thread.is_alive:
                    # The timeout value here doesn't matter so long as it's
                    # not infinite (ie, no arg)
                    thread.join(60) 
    except (KeyboardInterrupt, SystemExit):
        logging.info("Signaling stop_it to the threads")
        idle_checker.stop_it = idle_actor.stop_it = True
        trigger_event.set() # so trigger_thread (idle_actor) wakes up
        sys.exit()

if __name__ == "__main__":
    main()
