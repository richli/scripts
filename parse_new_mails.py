#!/usr/bin/env python
from __future__ import division, print_function
__author__ = 'Rich Li'
__version__ = 0.1

import argparse
import os.path
import mailbox

def main():
    """ Scan local maildirs for new mail
    
    For the local maildirs hardcoded below, we open each folder and scan for
    new messages. Info from the new messages (from, subject) is stored and
    then the total message count and new message count is diplayed for each
    account. The info from the new messages is also displayed.

    This is designed to be used as a tooltip for awesomewm.
    """
    # Parse args
    parser = argparse.ArgumentParser(description="Check maildirs for new mail")
    parser.add_argument('--show_all', action='store_true',
            help='Display info from all mailboxes, otherwise only new mail')
    parser.add_argument('--version', action='version', 
            version='%(prog)s version {}'.format(__version__))
    args = parser.parse_args()

    #
    mailroot = '/home/earl/.mutt/offlineimap'
    mailaccounts = ['dranek', 'mers', 'onion.avenger', 'rich.lindsley',
            'richli.ff']

    for acct in mailaccounts:
        inbox = mailbox.Maildir(os.path.join(mailroot, acct, 'INBOX'),
                create=False, factory=None)

        # Find new messages, store some info about them
        new_cnt = 0
        new_text = {}
        for msg in inbox.itervalues():
            if 'S' not in msg.get_flags():
                new_cnt += 1
                #msg_text = ["{}".format(new_cnt)]
                msg_text = []
                if 'from' in msg:
                    msg_text.append("  From: {}".format(msg['from']))
                if 'subject' in msg:
                    msg_text.append("  Subject: {}".format(msg['subject']))
#                if 'date' in msg:
#                    print("Date: {}".format(msg['date']))
                msg_text.append("----")
                new_text[new_cnt] = "\n".join(msg_text)

        # Display totals, info from new messages
        if args.show_all:
            if new_cnt:
                print("{}: {}/{}".format(acct, new_cnt, len(inbox)))
                for msg in new_text.values():
                    print(msg)
            else:
                print("{}: {}".format(acct, len(inbox)))
        else:
            if new_cnt:
                print("{} new mail on {}".format(new_cnt, acct))
                for msg in new_text.values():
                    print(msg)

if __name__ == "__main__":
    main()
