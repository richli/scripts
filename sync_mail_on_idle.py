#!/usr/bin/env python
__author__ = 'Rich Li'
__version__ = 2.4

""" Monitors mail folders for changes using IDLE and then runs offlineimap

The mail configuration (login details, folders) are specified with an ini-style
config.

This only runs on Python 3, not Python 2 (tested on Python 3.3)

TODO
----

* If a thread gets a network error or otherwise dies, I need to restart it
* Sometimes I'll get a socket error (seems to be on gmail usually) in a thread
but no output from it until I kill it. But in the meantime, CPU usage shoots to
100%.

"""

# Version history
# v2.0 2014-01-16: Lots of rewriting, moved to imaplib in standard library
# v2.1 2014-01-16: Fix bug where it checked for the initial imap response more
# v2.2 2014-01-17: Fix bugs with timing out properly
# v2.3 2014-01-17: Don't trigger the same account too many times too quickly
# v2.4 2014-03-28: Per-account timeouts

# all these are from stdlib
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
            now = time.time()
            if (now - self.last_print) >= 5*60 :
                msg = "{}: idling at {}".format(self.name, time.strftime("%d %b %I:%M:%S"))
                if self.timeout:
                    msg += ", {:0.1f} min since last sync".format((now - self.last_sync)/60)
                    msg += ", at most {:0.1f} min until next sync".format((self.timeout - now + self.last_sync)/60)
                logging.info(msg)
                self.last_print = now

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
            # (the smaller of time left until sync timeout, time remaining in current idle
            # command, and time left until next status print)
            now = time.time()
            until_print = now - self.last_print
            until_sync = now - self.last_sync
            until_idle = now - self.last_idle
            waittime = min(self.timeout - until_sync, 28*60 - until_idle, 5*60 - until_print)
            logging.debug("{}: time since issued IDLE is {:0.1f} minutes, since last sync is {:0.1f} minutes".format(self.name, until_idle/60, until_sync/60))
            if waittime < 0:
                logging.warning("{}: waittime is < 0, time since last idle is {:0.1f} seconds".format(self.name, now - self.last_idle))
                waittime = 10
            logging.debug("{}: Idling, waiting for {:0.1f} min".format(self.name, waittime/60))
            readlist, _, _ = select.select([server.socket(), self.stop_signal], [], [], waittime)

            # Check if we need to exit
            if self.stop_it:
                logging.info("{}: Terminating thread".format(self.name))
                break

            # Check IDLE response
            for sock in readlist:
                sock_msg_raw = sock.read().decode().strip()
                for sock_msg in sock_msg_raw.splitlines():
                    if sock_msg.startswith("* OK"):
                        # The IMAP server is just saying OK once in a while,
                        # nothing's wrong
                        # (dovecot seems especially noisy in doing this every few
                        # minutes)
                        logging.debug("{}: everything is okay ({})".format(self.name, sock_msg))
                    elif "EXISTS" in sock_msg.split():
                        # exists: number of messages in mailbox
                        logging.info("{}: new mail detected ({})".format(self.name, sock_msg))
                        self.mail_queue.put(self.mail_acct)
                        self.last_sync = self.last_print = time.time()
                    elif "RECENT" in sock_msg.split():
                        # recent: new mail, this session is the first to see it
                        # for mail checking purposes, this is redundant since a
                        # new mail will trigger both "recent" and "exists"
                        # (dovecot does this) or "exists" only (gmail doesn't
                        # support recent)
                        logging.debug("{}: new mail detected, but ignoring this response ({})".format(self.name, sock_msg))
                    elif "FETCH" in sock_msg.split():
                        # fetch: something about the message changed (flags, etc)
                        logging.info("{}: mail status changed ({})".format(self.name, sock_msg))
                        self.mail_queue.put(self.mail_acct)
                        self.last_sync = self.last_print = time.time()
                    elif "EXPUNGE" in sock_msg.split():
                        # expunge: message deleted (expunged) from mailbox
                        logging.info("{}: mail deleted ({})".format(self.name, sock_msg))
                        self.mail_queue.put(self.mail_acct)
                        self.last_sync = self.last_print = time.time()
                    elif sock_msg.startswith("* BYE"):
                        logging.warning("{}: Server kicked me out ({})".format(self.name, sock_msg))
                        self.stop_it = True
                        break
                    else:
                        logging.error("{}: I don't know how to handle this ({})".format(self.name, sock_msg))
                        self.stop_it = True
                        break

            # Finish IDLE if it's been long enough (28 minutes)
            if time.time() - self.last_idle >= 28*60:
                logging.debug("{}: Finishing IDLE command".format(self.name))
                server.send("DONE\r\n".encode())
                self.last_idle = None
                resp = server.readline().decode()
                # The response is probably something like "OK IDLE terminated"
                # but why bother checking it

            # Sync anyway if it's been long enough
            now = time.time()
            if (now - self.last_sync) > self.timeout:
                logging.info("{}: Triggering due to timeout exceeded ({:0.1f} minutes)".format(self.name, (now - self.last_sync) / 60))
                self.mail_queue.put(self.mail_acct)
                self.last_sync = self.last_print = now

        # We're out of the while-True loop
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
        # If the same account is triggered multiple times quickly (e.g.,
        # multiple folders within the same account have updates), then this
        # ignores subsequent triggers for a time period of remember_time (in
        # seconds). last_sync is a dict that keeps track of the last time each
        # account was synced.
        self.remember_time = 20  # seconds
        self.last_sync = {} 
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

            # Check if it's been long enough for this account to trigger
            now = time.time()
            acct_time = self.last_sync.get(acct, now - self.remember_time - 10)

            if (now - acct_time) > self.remember_time:
                # Run offlineimap for the accounts
                logging.info("Syncing {} at {}".format(acct, time.strftime("%d %b %I:%M:%S")))
                cmd = ["/usr/bin/offlineimap", "-o", "-a", acct, "-k", "mbnames:enabled=no"]
                logging.debug("Calling {}".format(cmd))
                # NB: offlineimap actually outputs to stderr, not stdout
                cmd_out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
                #print(cmd_out)
                self.last_sync[acct] = now
            else:
                logging.debug("{}: won't trigger {} since it was {:0.1f} seconds from the last time it triggered".format(self.name, acct, now - acct_time))


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
            #level=logging.DEBUG,
            format='%(levelname)s: %(message)s',
            #format='%(asctime)s %(levelname)s: %(message)s',
            #filename='/home/earl/.local/bin/idle_sync.log',
            )

    # Read in account info
    cfg = configparser.ConfigParser()
    cfg.read('idle_mail.ini')

    # Create the consumer thread and its event it watches
    mail_queue = queue.Queue()
    trigger_thread = idle_actor(mail_queue, "trigger")
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
        mail_timeout = cfg.get(acct, "timeout", fallback=10)
        mail_timeout = 60 * int(mail_timeout) # convert minutes to seconds

        for folder_i, folder in enumerate(mail_folders.split(",")):
            thread_name='{}_{}'.format(acct, folder.strip())
            mail_idle = idle_checker(mail_queue, acct, mail_user, mail_pass,
                    mail_server, folder.strip(), pipe_signal[0], thread_name,
                    mail_timeout)
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
                else:
                    print("HEY, LISTEN! {} is dead!".format(thread.name))
    except (KeyboardInterrupt, SystemExit):
        logging.debug("Signaling stop_it to the threads")
        trigger_thread.stop()
        for t in idle_threads:
            t.stop()
        os.write(pipe_signal[1], "stop".encode())
        #sys.exit()

if __name__ == "__main__":
    main()
