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
    mail_info = []
    
    # Connect to MERS
    mail_info.append({
    'user': "xxx",
    'pass': "xxx",
    'server': "xxx.edu"
    })
    # Connect to dranek
    mail_info.append({
    'user': "xxx",
    'pass': "xxx",
    'server': "xxx.com"
    })

    for m in mail_info:
        print("Connecting to {}...".format(m['server']), end='')
        mail = imaplib.IMAP4_SSL(m['server'])
        ret = mail.login(m['user'], m['pass'])
        check_imap_return(ret, "done", "Login failed")

        # Get quota info
        ret = mail.getquotaroot("inbox")
        check_imap_return(ret, None, "Quota lookup failed")
        quota_parse = ret[1][1][0].decode().rpartition("STORAGE")[2].strip().split(" ")
        quota_used = int(quota_parse[0])
        quota_total = quota_parse[1]
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

