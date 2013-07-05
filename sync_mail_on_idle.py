#!/usr/bin/env python2
from __future__ import division, print_function
__author__ = 'Rich Li'
__version__ = 0.5

import sys
import argparse
import threading

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
        self.timeout = 20 # DEBUG

    def run(self):
        server = self.server
        select_info = server.select_folder(self.mail_folder)
        while True:
            print("{}: idling".format(self.name))
            server.idle()
            idle_response = server.idle_check(timeout=self.timeout)
            server.idle_done()
            server.noop()

            # Check if we need to exit
            if idle_checker.stop_it:
                print("{}: Terminating thread".format(self.name))
                break

            # TODO: check idle_response. Don't need to trigger offlineimap
            # in all cases (eg, expunge, no action, etc)
            # But maybe I could still trigger at least an hour or something
            # (use time module for this)
            print(idle_response)
            print("{}: Triggering".format(self.name))
            idle_actor.accts.append(self.mail_acct)
            self.trigger_event.set()
            self.trigger_event.clear()

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
            print("{}: triggered".format(self.name))

            # Check if we need to exit
            if idle_actor.stop_it:
                print("{}: Terminating thread".format(self.name))
                break

            # Run offlineimap for the accounts
            while len(idle_actor.accts) > 0:
                acct = idle_actor.accts.pop()
                print("/usr/bin/offlineimap -o -a {}".format(acct))
                # TODO: Actually execute this

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

    mail_info = {}
    idle_threads = []

    ####
    # TODO: Put this info in a separate config file?
    mail_info['accts'] = ["foo", "bar"] # offlineimap account names
    # Connect to foo
    mail_info['foo_user'] = "foo@example.com"
    mail_info['foo_pass'] = "nothing"
    mail_info['foo_server'] ="mail.example.com"
    mail_info['foo_folders'] = ["INBOX", "old", "sub/folder"]

    # Connect to bar
    mail_info['bar_user'] = "bar"
    mail_info['bar_pass'] = "something"
    mail_info['bar_server'] ="mail.bar.com"
    mail_info['bar_folders'] = ["INBOX"]
    ####

    # Create the consumer thread and its event it watches
    trigger_event = threading.Event()
    trigger_thread = idle_actor(trigger_event)
    trigger_thread.name = "idle-actor"
    trigger_thread.start()

    # Create the producer threads
    for acct in mail_info['accts']:
        mail_user = mail_info['{}_user'.format(acct)]
        mail_pass = mail_info['{}_pass'.format(acct)]
        mail_server = mail_info['{}_server'.format(acct)]
        for folder in mail_info['{}_folders'.format(acct)]:
            thread_name='{}_{}'.format(acct, folder)
            print("Spawning {}".format(thread_name))
            mail_idle = idle_checker(trigger_event, acct, mail_user,
                    mail_pass, mail_server, folder)
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
        print("Signaling stop_it to the threads")
        idle_checker.stop_it = idle_actor.stop_it = True
        trigger_event.set() # so trigger_thread (idle_actor) wakes up
        sys.exit()

if __name__ == "__main__":
    main()
