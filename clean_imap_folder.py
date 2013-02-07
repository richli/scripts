#!/usr/bin/env python
from __future__ import division, print_function
__author__ = 'Rich Li'
__version__ = 0.1
""" Deletes all mails in an IMAP folder and then expunges them """

import imaplib

def main():
    # Connect to MERS
    mail_user = "XXX"
    mail_pass = "XXX"
    print("Logging in")
    mers = imaplib.IMAP4_SSL("mail.mers.byu.edu")
    ret = mers.login(mail_user, mail_pass)
    print(ret)

    # Get quota info
    ret = mers.getquota("")
    if ret[0] == "OK":
        quota_parse = ret[1][0].decode().split(" ")
        quota_used = int(quota_parse[2])
        quota_total = quota_parse[3]
        # Trim close parens off 
        quota_total = int(quota_total.rstrip(")"))
        print("Quota: {:0.0f}/{:0.0f} MiB {:0.0f}%".format(quota_used/1024, quota_total/1024,
            quota_used/quota_total * 100))
    else:
        print("Quota lookup failed: {}".format(ret))

    #ret = mers.list()
    #print(ret)

    # Select the mailbox to purge
    # (Note that for mailboxes with spaces, the IMAP mailbox name must be
    # double-quote-enclosed
    ret = mers.select('"qsub mails"')
    if ret[0] == "OK":
        mail_count = int(ret[1][0].decode())
        print("{} mails present".format(mail_count))
        search_ret = mers.search(None, "All")

        # Loop through messages, mark deleted
        if search_ret[0] == "OK":
            msgnums = search_ret[1][0].decode().split(" ")
            msg_count = 0
            for msg in msgnums:
                print("\rMarking {} deleted".format(msg), end=' ')
                del_ret = mers.store(msg, "+FLAGS", "\\Deleted")
                msg_count += 1
                if msg_count > 2000:
                    break

        # Expunge mailbox, close it
        ret = mers.expunge()
        print(ret)
        ret = mers.close()
        print(ret)

    else:
        print("Mail select failed: {}".format(ret))

    # Logout
    print("Logging out")
    ret = mers.logout()
    print(ret)

if __name__ == "__main__":
    main()

