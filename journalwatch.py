#!/usr/bin/env python
"""Find notable content in the journal and email it.

Tested with Python 3.4

Inspired by: https://tim.siosm.fr/blog/2014/02/24/journald-log-scanner-python/

"""
__author__ = 'Rich Li'
__version__ = 0.3

# Version history:
# v0.1 2014-06-14: Started
# v0.2 2014-07-01: Updated to group output from various services
# v0.3 2015-03-06: Switch to attic instead of obnam

import argparse
from datetime import datetime, timedelta
import re
import json
from email import charset
from email.mime.text import MIMEText
import email.utils
import ssl
from smtplib import SMTP

from systemd import journal


def main():
    """Main function."""
    #################
    # Parse arguments
    #################
    parser = argparse.ArgumentParser(
        description='Emails notable events in the journal')
    parser.add_argument('--config', '-c', action='store',
                        default='journalwatch.json',
                        help='json config file (default: %(default)s)')
#    parser.add_argument('--show-config', action='store_true',
#                        help="Display parsed configuration file")
    parser.add_argument('--no-send', action='store_true',
                        help="Don't send email, just print it")
    parser.add_argument('--version', action='version',
                        version='%(prog)s version {}'.format(__version__))
    args = parser.parse_args()

    # Load config file
    with open(args.config) as f:
        config = json.load(f)

    #################
    # Define patterns to ignore
    #################
    # Those are for matching dynamically named units:
    user_session = re.compile("user@\d+.service")
    session = re.compile("session-[a-z]?\d+.scope")
    ssh_unit = re.compile("sshd@[0-9a-f.:]*")

    # Those will match the logged message itself:
    btsync_deverr = re.compile("UPnP: Device error.*")
    journal_restart = re.compile("Journal (started|stopped)")
    login_buttons = re.compile("Watching system buttons .*")
    attic_backup = re.compile("Archive fingerprint: .*")
    packages_found = re.compile("Packages \((\d+)\).*")
    # sshSocketStart = re.compile("(Starting|Stopping) OpenSSH Per-Connection Daemon.*")
    # ssh_pubkey = re.compile("Accepted publickey for (earl|git).*")
    # sshReceivedDisconnect = re.compile("Received disconnect from.*")
    # logindNewSession = re.compile("New session [a-z]?\d+ of user (bob|alice).*")
    # sshdSessionClosed = re.compile(".*session closed for user (bob|alice).*")
    # sessionOpenedRoot = re.compile(".*session opened for user root.*")
    # suSessionClosedGit = re.compile(".*session opened for user git.*")
    # anacronNormalExit = re.compile("Normal exit (\d+ jobs run).*")
    # postfixStatistics = re.compile("statistics:.*")
    # postfixHostnameDoesNotResolve = re.compile("warning: hostname .* does not resolve to address .*: Name or service not known")

    #################
    # Ready the journal
    #################
    j = journal.Reader()
    j.log_level(journal.LOG_INFO)
    # TODO: Find when the last time this was run instead
    yesterday = datetime.now() - timedelta(days=1, minutes=10)
    j.seek_realtime(yesterday)

    mail_content = []
    service_entries = {key: [] for key in
                       ('attic', 'pacupdate', 'timesyncd', 'sshd')}
    attic_count = 0
    package_count = None

    #################
    # Scan through the journal, filter out anything notable
    #################
    for entry in j:
        # A log doesn't have a message...? weird
        if 'MESSAGE' not in entry:
            line = '{} {}[{}]: empty'
            line = line.format(datetime.ctime(entry['__REALTIME_TIMESTAMP']),
                               entry['PRIORITY'], entry['SYSLOG_IDENTIFIER'])
            mail_content.append(line)

        # With systemd unit name
        elif '_SYSTEMD_UNIT' in entry:
            if entry['_SYSTEMD_UNIT'] in ("udisks.service",
                                          "polkit.service",
                                          "avahi-daemon.service",
                                          "bluetooth.service",
                                          "accounts-daemon.service",
                                          "rtkit-daemon.service",
                                          "dbus.service",
                                          "lightdm.service",
                                          "systemd-udevd.service",
                                          "envoy@ssh-agent.service",
                                          "mkinitcpio-generate-shutdown-ramfs.service"):
                pass
            elif user_session.match(entry['_SYSTEMD_UNIT']):
                pass
            elif "btsync" in entry['_SYSTEMD_UNIT']:
                if btsync_deverr.match(entry['MESSAGE']):
                    pass
            elif entry['_SYSTEMD_UNIT'] == 'systemd-journald.service':
                if journal_restart.match(entry['MESSAGE']):
                    pass
            elif entry['_SYSTEMD_UNIT'] == 'systemd-logind.service':
                if login_buttons.match(entry['MESSAGE']):
                    pass
            elif session.match(entry['_SYSTEMD_UNIT']):
                pass
#            elif sshUnit.match(entry['_SYSTEMD_UNIT']):
#                if sshAcceptPublicKey.match(entry['MESSAGE']):
#                    pass
#                elif sshReceivedDisconnect.match(entry['MESSAGE']):
#                    pass
#            elif entry['_SYSTEMD_UNIT'] == "systemd-logind.service":
#                if logindNewSession.match(entry['MESSAGE']):
#                    pass
#            elif entry['_SYSTEMD_UNIT'] == "postfix.service":
#                if postfixHostnameDoesNotResolve.match(entry['MESSAGE']):
#                    pass
            # Attic
            elif "attic" in entry['_SYSTEMD_UNIT']:
                if attic_backup.match(entry['MESSAGE']):
                    attic_count += 1

                service_entries['attic'].append('U %s %s %s %s[%s]: %s' % (
                    entry['__REALTIME_TIMESTAMP'].strftime("%a %b %d %I:%m:%S %p"),
                    entry['PRIORITY'],
                    entry['_SYSTEMD_UNIT'],
                    entry.get('SYSLOG_IDENTIFIER', 'UNKNOWN'),
                    entry['_PID'],
                    entry['MESSAGE']
                ))

            # Count packages
            elif entry['_SYSTEMD_UNIT'] == 'pacupdate.service':
                match = packages_found.match(entry['MESSAGE'])
                if match:
                    package_count = match.group(1)

                service_entries['pacupdate'].append('U %s %s %s %s[%s]: %s' % (
                    entry['__REALTIME_TIMESTAMP'].strftime("%a %b %d %I:%m:%S %p"),
                    entry['PRIORITY'],
                    entry['_SYSTEMD_UNIT'],
                    entry.get('SYSLOG_IDENTIFIER', 'UNKNOWN'),
                    entry['_PID'],
                    entry['MESSAGE']
                ))

            # timesyncd
            elif entry['_SYSTEMD_UNIT'] == 'systemd-timesyncd.service':
                service_entries['timesyncd'].append('U %s %s %s %s[%s]: %s' % (
                    entry['__REALTIME_TIMESTAMP'].strftime("%a %b %d %I:%m:%S %p"),
                    entry['PRIORITY'],
                    entry['_SYSTEMD_UNIT'],
                    entry.get('SYSLOG_IDENTIFIER', 'UNKNOWN'),
                    entry['_PID'],
                    entry['MESSAGE']
                ))

            # sshd
            elif ssh_unit.match(entry['_SYSTEMD_UNIT']):
                service_entries['sshd'].append('U %s %s %s %s[%s]: %s' % (
                    entry['__REALTIME_TIMESTAMP'].strftime("%a %b %d %I:%m:%S %p"),
                    entry['PRIORITY'],
                    entry['_SYSTEMD_UNIT'],
                    entry.get('SYSLOG_IDENTIFIER', 'UNKNOWN'),
                    entry['_PID'],
                    entry['MESSAGE']
                ))

            else:
                mail_content.append('U %s %s %s %s[%s]: %s' % (
                    entry['__REALTIME_TIMESTAMP'].strftime("%a %b %d %I:%m:%S %p"),
                    entry['PRIORITY'],
                    entry['_SYSTEMD_UNIT'],
                    entry.get('SYSLOG_IDENTIFIER', 'UNKNOWN'),
                    entry['_PID'],
                    entry['MESSAGE']
                ))

        # With syslog identifier only
        elif entry['SYSLOG_IDENTIFIER'] in ("systemd",
                                            "kernel",
                                            "bluetoothd",
                                            "systemd-sysctl",
                                            "systemd-journald",
                                            "systemd-udevd",
                                            "ntpd", "mtp-probe"):
            pass
#            if sshSocketStart.match(entry['MESSAGE']):
#                pass
#            # elif firewalldStart.match(entry['MESSAGE']):
#            #     pass
#        elif entry['SYSLOG_IDENTIFIER'] == "sshd":
#            if sshdSessionClosed.match(entry['MESSAGE']):
#                pass
#        elif entry['SYSLOG_IDENTIFIER'] == "sudo":
#            if sessionOpenedRoot.match(entry['MESSAGE']):
#                pass
#        elif entry['SYSLOG_IDENTIFIER'] == "postfix/anvil":
#            if postfixStatistics.match(entry['MESSAGE']):
#                pass
#        elif entry['SYSLOG_IDENTIFIER'] == "su":
#            if suSessionClosedGit.match(entry['MESSAGE']):
#                pass
        else:
            mail_content.append('S %s %s %s: %s' % (
                entry['__REALTIME_TIMESTAMP'].strftime("%a %b %d %I:%m:%S %p"),
                entry['PRIORITY'],
                entry.get('SYSLOG_IDENTIFIER', 'UNKNOWN'),
                entry['MESSAGE']
            ))

    # Create summary message
    mail_summary = "Daily journalwatch\n\n"
    if attic_count:
        mail_summary += "attic backed up {} times,".format(attic_count)
    if package_count:
        mail_summary += "pacupdate found {} packages to update\n".format(package_count)

    for service in ('attic', 'pacupdate', 'sshd', 'timesyncd'):
        mail_summary += '\n=====================\n'
        mail_summary += '{} logs:\n'.format(service)
        mail_summary += '\n'.join(service_entries[service])
        mail_summary += '\n'

    mail_summary += '\n=====================\n'
    mail_summary += "Remaining filtered log from {} to now follows:\n".format(yesterday)
    # TODO: Also count ssh, nginx, dovecot, postfix info (logins passed and failed, etc)

    #################
    # Send email
    #################
    # Make sure UTF-8 is quoted-printable, not base64
    # http://stackoverflow.com/questions/9403265/how-do-i-use-python-3-2-email-module-to-send-unicode-messages-encoded-in-utf-8-w/9509718#9509718
    charset.add_charset('utf-8', charset.QP, charset.QP)
    mail = MIMEText(mail_summary + '\n'.join(mail_content))

    mail['Subject'] = config['subject']
    mail['To'] = config['to']
    mail['From'] = config['from']
    mail['Date'] = email.utils.formatdate(localtime=True)
    mail['Message-ID'] = email.utils.make_msgid()
    mail['User-Agent'] = __file__
    if args.no_send:
        print(mail.as_string())
    else:
        tls_context = ssl.create_default_context()
        tls_context.check_hostname = True
        with SMTP(config['smtp_host'],
                  config['smtp_port']) as smtp:
            # smtp.set_debuglevel(True)
            smtp.starttls(context=tls_context)
            smtp.login(config['smtp_user'],
                       config['smtp_pass'])
            smtp.send_message(mail)

    return


if __name__ == '__main__':
    main()
