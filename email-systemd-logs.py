#!/usr/bin/env python
""" Emails the output of various systemd units from the journal

Tested with Python 3.4

The configuration is stored in a yaml file. It goes through each systemd
service listed and emails the output since the specified time.

Sample YAML configuration file:

# Configuration file for email-systemd-logs.py
mail:
    email_dest: 'from@example.com'
    email_from: 'to@example.com'
    smtp_host: 'mail.example.com'
    smtp_port: '587'
    smtp_user: 'from@example.com'
    smtp_pass: "secret password"
services:
    - name: paccache
      last_run: yesterday
    - name: logwatch
      last_run: -3h

"""
__author__ = 'Rich Li'
__version__ = 0.1

# Version history:
# v0.1 2014-04-05: Started

import sys
import argparse
import subprocess
import yaml
from email.message import Message
import email.utils
import ssl
from smtplib import SMTP
import pprint


def main():
    #################
    # Parse arguments
    #################
    parser = argparse.ArgumentParser(description='Emails systemd logs')
    parser.add_argument('--config', action='store',
                        default='email-systemd-logs.yaml',
                        help='yaml config file to read')
    parser.add_argument('--show-config', action='store_true',
                        help="Display parsed configuration file")
    parser.add_argument('--no-send', action='store_true',
                        help="Don't send email, just print it")
    parser.add_argument('--version', action='version',
                        version='%(prog)s version {}'.format(__version__))
    args = parser.parse_args()

    #################
    # Load config
    #################
    with open(args.config) as f:
        config = yaml.load(f, Loader=yaml.CSafeLoader)
        if args.show_config:
            pprint.pprint(config)

    #################
    # Send emails
    #################
    for service in config['services']:
        # Query the journal
        cmd = ["journalctl", "-u", service['name'], "--since",
               service['last_run'], "--no-pager"]
        j_out = subprocess.check_output(cmd).decode()

        # Create the email
        msg = Message()
        msg['Subject'] = service['name']
        msg['To'] = config['mail']['email_dest']
        msg['From'] = config['mail']['email_from']
        msg['Date'] = email.utils.formatdate(localtime=True)
        msg['Message-ID'] = email.utils.make_msgid()
        msg['User-Agent'] = sys.argv[0]
        msg_text = ' '.join(cmd) + '\n' + j_out
        msg.set_payload(msg_text)

        if args.no_send:
            print(msg)
        else:
            # Send via SMTP
            tls_context = ssl.create_default_context()
            tls_context.check_hostname = True
            with SMTP(config['mail']['smtp_host'],
                      config['mail']['smtp_port']) as smtp:
                # smtp.set_debuglevel(True)
                smtp.starttls(context=tls_context)
                smtp.login(config['mail']['smtp_user'],
                           config['mail']['smtp_pass'])
                smtp.send_message(msg)

if __name__ == '__main__':
    main()
