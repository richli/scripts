#!/usr/bin/env python
__author__ = 'Rich Li'
__version__ = 2.1

""" Monitors mail folders for changes using IDLE and then runs offlineimap

The mail configuration (login details, folders) are specified with an ini-style
config.

This only runs on Python 3, not Python 2 (tested on Python 3.3)

TODO: If a thread gets a network error, I need to restart it

TODO: Don't run offlineimap for the same account if it's been less
than a few seconds since the last account

"""

# Version history
# v2.0 2014-01-16: Lots of rewriting, moved to imaplib in standard library
# v2.1 2014-01-16: Fix bug where it checked for the initial imap response more
# than once

# all stdlib imports
import sys, os
import argparse
import configparser
import threading
import logging
import select
import queue
import time
import imaplib
import subprocess

class idle_checker(threading.Thread):
    """ This checks an IMAP folder using IDLE 

    As many instances of this class (threads) need to be created as IMAP
    folders to be checked
    
    """

    def __init__(self, mail_queue, mail_acct, mail_user, mail_pass,
            mail_server, mail_folder, stop_signal, name, timeout=None):
        """ Initializes the thread

        mail_queue: a queue object to use when an account is triggered
        mail_acct: the offlineimap account name
        mail_user: IMAP username 
        mail_pass: IMAP password
        mail_server: IMAP hostname (SSL is assumed yes)
        mail_folder: IMAP foldername
        timeout: max time (in seconds) until it syncs anyway. If None, then
        forever (so only syncs on IDLE)

        """
        super(idle_checker, self).__init__()

        self.mail_queue = mail_queue
        self.mail_acct = mail_acct
        self.mail_user = mail_user
        self.mail_pass = mail_pass
        self.mail_server = mail_server
        self.mail_folder = mail_folder
        self.stop_signal = stop_signal
        self.name = name
        self.timeout = timeout

        # Connect
        self.server = imaplib.IMAP4_SSL(mail_server)

        self.last_sync = time.time()
        self.last_print = time.time()
        self.last_idle = None
        self.running = True # whether we're currently running ok
        self.stop_it = False # whether it's time to stop and clean up
        logging.info("Spawned {}".format(self.name))

    def stop(self):
        self.stop_it = True

    def run(self):
        server = self.server
        server.login(self.mail_user, self.mail_pass)
        select_info = server.select(self.mail_folder)

        while True:
            # Display status periodically
            if (time.time() - self.last_print) / 60 >= 5 :
                msg = "{}: idling at {}".format(self.name, time.strftime("%d %b %I:%M:%S"))
                if self.timeout:
                    msg += ", {:0.1f} min since last sync".format((time.time() - self.last_sync)/60)
                logging.info(msg)
                self.last_print = time.time()

            if not self.last_idle:
                # Start IDLE if we haven't already
                logging.debug("{}: Sent IDLE command".format(self.name))
                server.send("a IDLE\r\n".encode())
                self.last_idle = time.time()

                # Expect initial response
                resp = server.readline().decode()
                if not resp.startswith("+"):
                    raise Exception("{}: Unexpected response: {}".format(self.name, resp))

            # Wait for further response
            waittime = self.timeout - (time.time() - self.last_idle)
            logging.debug("{}: Idling, blocking for {:0.1f} seconds".format(self.name, waittime))
            readlist, _, _ = select.select([server.socket(), self.stop_signal], [], [], waittime)

            # Check if we need to exit
            if self.stop_it:
                logging.info("{}: Terminating thread".format(self.name))
                break

            # Check IDLE response
            for sock in readlist:
                sock_msg = sock.read().decode()
                if sock_msg.startswith("* OK"):
                    # The IMAP server is just saying OK once in a while,
                    # nothing's wrong
                    pass
                elif "EXISTS" in sock_msg.split():
                    # exists: number of messages in mailbox
                    logging.info("{}: new mail detected ({})".format(self.name, sock_msg))
                    self.mail_queue.put(self.mail_acct)
                    self.last_sync = time.time()
                elif "FETCH" in sock_msg.split():
                    # fetch: something about the message changed (flags, etc)
                    logging.info("{}: mail status changed ({})".format(self.name, sock_msg))
                    self.mail_queue.put(self.mail_acct)
                    self.last_sync = time.time()
                elif "EXPUNGE" in sock_msg.split():
                    # expunge: message deleted (expunged) from mailbox
                    logging.info("{}: a mail deleted ({})".format(self.name, sock_msg))
                    self.mail_queue.put(self.mail_acct)
                    self.last_sync = time.time()
                else:
                    logging.warning("{}: I don't know how to handle this ({})".format(self.name, sock_msg))

            # Finish IDLE if it's been long enough (28 minutes)
            if time.time() - self.last_idle >= 28*60:
                logging.debug("{}: Finishing IDLE command".format(self.name))
                server.send("DONE\r\n".encode())
                self.last_idle = None

            # Sync anyway if it's been long enough
            if (time.time() - self.last_sync) > self.timeout:
                logging.info("{}: Triggering due to timeout exceeded ({:0.1f} minutes)".format(self.name, (time.time() - self.last_sync) / 60))
                self.mail_queue.put(self.mail_acct)
                self.last_sync = time.time()


#            # Check idle_response. Don't need to trigger offlineimap
#            # in all cases.
#            for resp in idle_response:
#                #print(self.name, idle_response, resp)
#                #if isinstance(resp[0], (str,unicode)) and resp[0].upper().startswith("IDLE"):
#                #    continue
#                #if len(resp) < 2:
#                #    continue
#                if len(resp) < 2:
#                    logging.error("{}: resp is {}".format(self.name, resp))
#
#                # Trigger immediately for new mail
#                # For mail changes (flags, deletion), wait a little for things
#                # to settle
#                if resp[1] in (u'RECENT', u'EXISTS'):
#                    # recent: new mail
#                    # exists: number of messages in mailbox
#                    # NB: it seems dovecot uses "recent" and gmail uses "exists"
#                    logging.info("{}: Triggering due to {}".format(self.name, resp[1]))
#                    idle_actor.accts.append(self.mail_acct)
#                    self.trigger_event.set()
#                    self.last_sync = time.time()
#                elif resp[1] in (u'FETCH', u'EXPUNGE'):
#                    # fetch: something about the message changed (flags, etc)
#                    # expunge: message deleted (expunged) from mailbox
#                    # NB: while dovecot will notify on flag changes using "fetch", gmail does not
#                    logging.info("{}: Triggering (delayed) due to {}".format(self.name, resp[1]))
#                    time.sleep(10)
#                    idle_actor.accts.append(self.mail_acct)
#                    self.trigger_event.set()
#                    self.last_sync = time.time()
#                elif resp[1] in (u'Still here'):
#                    # These responses don't need an offlineimap sync
#                    #logging.info("{}: No action due to {}".format(self.name, resp[1]))
#                    pass
#                else:
#                    # TODO: Any other cases happen?
#                    logging.warning("{} UNKNOWN idle response: {}".format(self.name,resp))
#

        # Get out of IDLE
        if self.last_idle:
            logging.debug("{}: Finishing IDLE command".format(self.name))
            server.send("DONE\r\n".encode())
            self.last_idle = None
            msg = server.readline()

        logging.debug("{}: Closing mailbox".format(self.name))
        server.close()
        logging.debug("{}: Logging out".format(self.name))
        server.logout()
        logging.info("{}: Finished".format(self.name))

class idle_actor(threading.Thread):
    """ This triggers offlineimap 
    
    Only one instance of this class (thread) is needed
    
    """

    def __init__(self, idle_queue, name):
        super(idle_actor, self).__init__()
        self.idle_queue = idle_queue
        self.stop_it = False
        self.name = name
        logging.info("Spawned {}".format(self.name))

    def stop(self):
        self.stop_it = True
        # Add a dummy item to the queue so it wakes up the thread
        self.idle_queue.put("_stop")

    def run(self):
        while True:
            acct = self.idle_queue.get()
            logging.debug("{}: got an item from the queue".format(self.name))

            # Check if we need to exit
            if self.stop_it:
                logging.info("{}: Terminating thread".format(self.name))
                break

            # Run offlineimap for the accounts
            cmd = ["/usr/bin/offlineimap", "-o", "-a", acct, "-k", "mbnames:enabled=no"]
            logging.info("Calling {}".format(cmd))
            # NB: offlineimap actually outputs to stderr, not stdout
            cmd_out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            #print(cmd_out)

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
    cfg = configparser.ConfigParser()
    cfg.read('idle_mail.ini')

    # Create the consumer thread and its event it watches
    mail_queue = queue.Queue()
    trigger_thread = idle_actor(mail_queue, "oimap_trigger")
    trigger_thread.start()

    # Create a self pipe, it's used as a signal to the producer threads
    pipe_signal = os.pipe2(os.O_NONBLOCK)

    # Create the producer threads
    idle_threads = []
    for acct in cfg.sections():
        mail_user = cfg.get(acct, "user")
        mail_pass = cfg.get(acct, "pass")
        mail_server = cfg.get(acct, "server")
        mail_folders = cfg.get(acct, "folders")
        timeout = 10*60 # Check at least once every 10 minutes

        for folder_i, folder in enumerate(mail_folders.split(",")):
            thread_name='{}_{}'.format(acct, folder.strip())
            mail_idle = idle_checker(mail_queue, acct, mail_user, mail_pass,
                    mail_server, folder.strip(), pipe_signal[0], thread_name, timeout)
            idle_threads.append(mail_idle)
            mail_idle.start()

    # Watch for SIGINT and terminate gracefully
    try:
        while True:
            for thread in idle_threads:
                if thread.is_alive:
                    # The timeout value here doesn't matter so long as it's
                    # not infinite (ie, no arg)
                    thread.join(60) 
    except (KeyboardInterrupt, SystemExit):
        logging.debug("Signaling stop_it to the threads")
        trigger_thread.stop()
        for t in idle_threads:
            t.stop()
        os.write(pipe_signal[1], "stop".encode())
        #sys.exit()

if __name__ == "__main__":
    main()
