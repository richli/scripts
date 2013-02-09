#!/usr/bin/env python
from __future__ import division, print_function
__author__ = 'Rich Li'
__version__ = 0.2
""" Deletes all mails in an IMAP folder and then expunges them """

import sys
import imaplib

def check_imap_return(ret_msg, ok_string, bad_string):
    if ret_msg[0] == "OK" or ret_msg[0] == "BYE":
        if ok_string:
            print(ok_string)
        return True
    else:
        print(bad_string)
        print(ret_msg)
        sys.exit(1)
        return False

def main():
    # Connect to MERS
    mail_user = "XXX"
    mail_pass = "XXX"
    print("Connecting...", end='')
    mers = imaplib.IMAP4_SSL("mail.mers.byu.edu")
    ret = mers.login(mail_user, mail_pass)
    check_imap_return(ret, "done", "Login failed")

    # Get quota info
    ret = mers.getquota("")
    check_imap_return(ret, None, "Quota lookup failed")
    quota_parse = ret[1][0].decode().split(" ")
    quota_used = int(quota_parse[2])
    quota_total = quota_parse[3]
    # Trim close parens off 
    quota_total = int(quota_total.rstrip(")"))
    print("Quota: {:0.0f}/{:0.0f} MiB {:0.0f}%".format(quota_used/1024,
        quota_total/1024, quota_used/quota_total * 100))

    #ret = mers.list()
    #print(ret)

    # Select the mailbox to purge
    # (Note that for mailboxes with spaces, the IMAP mailbox name must be
    # double-quote-enclosed
    ret = mers.select('"qsub mails"')
    check_imap_return(ret, None, "Mail select failed")
    mail_count = int(ret[1][0].decode())
    print("{} mails present".format(mail_count))

    # Get a list of the message numbers
    # (Not needed since I can specify the unlimited range 1:* below)
    #search_ret = mers.search(None, "All")
    #check_imap_return(search_ret, None, "Mail search failed")
    #msgnums = search_ret[1][0].decode().split(" ")

    # Mark all messages as deleted
    del_ret = mers.store("1:*", "+FLAGS", "\\Deleted")
    check_imap_return(del_ret, "Marked {} messages as deleted".format(
        mail_count), "Mark deleted flags failed")

    # Expunge mailbox, close it
    ret = mers.expunge()
    check_imap_return(ret, "Expunge complete", "Expunge failed")

    ret = mers.close()
    check_imap_return(ret, "Mailbox closed", "Close failed")

    # Logout
    ret = mers.logout()
    check_imap_return(ret, "Logged out", "Logout failed")

if __name__ == "__main__":
    main()

