#!/usr/bin/env python
from __future__ import division, print_function
__author__ = 'Rich Li'
__version__ = 0.1
""" Queries quota space for an IMAP account """

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
    # Connect to dranek
    mail_user = "xxx"
    mail_pass = "xxx"
    mail_server="example.com"

    print("Connecting to {}...".format(mail_server), end='')
    mail = imaplib.IMAP4_SSL(mail_server)
    ret = mail.login(mail_user, mail_pass)
    check_imap_return(ret, "done", "Login failed")

    # Get quota info
    ret = mail.getquotaroot("inbox")
    check_imap_return(ret, None, "Quota lookup failed")
    quota_parse = ret[1][1][0].decode().split(" ")
    quota_used = int(quota_parse[3])
    quota_total = quota_parse[4]
    # Trim close parens off 
    quota_total = int(quota_total.rstrip(")"))
    print("Quota: {:0.0f}/{:0.0f} MiB {:0.0f}%".format(quota_used/1024,
        quota_total/1024, quota_used/quota_total * 100))

    #ret = mail.list()
    #print(ret)

    ## Close mailbox
    #ret = mail.close()
    #check_imap_return(ret, "Mailbox closed", "Close failed")

    # Logout
    ret = mail.logout()
    check_imap_return(ret, "Logged out", "Logout failed")

if __name__ == "__main__":
    main()

