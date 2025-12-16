#!/usr/bin/env python
import argparse
import logging

from src.backupreader import reader
from src.olk15parser import parser
from src.archiver import archiver
from src.helpers import helpers
from src.helpers import progress
from src.logger import config_logger

logger = config_logger.Logger()


def _parse_args():
    parser_cli = argparse.ArgumentParser(description='UBF8T346G9 Outlook parser')
    parser_cli.add_argument(
        '--mode',
        choices=['all', 'mail', 'calendar'],
        default='all',
        help='Select what to archive: all (default), mail, or calendar'
    )
    parser_cli.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Set log verbosity (default: INFO)'
    )
    return parser_cli.parse_args()


def run():
    args = _parse_args()
    config_logger.set_log_level(getattr(logging, args.log_level))

    profile_data_location = helpers.Helper.get_location()
    backupreader_app = reader.BackupReader(profile_data_location)
    olk15parser_app = parser.OLK15Parser()
    mail_archiver = archiver.MailArchiver()
    calendar_archiver = archiver.CalendarArchiver()

    if args.mode in ('all', 'mail'):
        mails_amount = backupreader_app.get_mails_amount()
        progressbar = progress.ProgressBar(mails_amount)

        mails = backupreader_app.get_mails_from_database()

        logger.logger.info('Getting email content and writing to files')
        for mail in mails:
            progressbar.update()
            mail_path = profile_data_location + mail.get('content_path')
            message = olk15parser_app.get_mail_content(mail_path, mail.get('subject'))
            mail_archiver.archive_mail(mail, message)

        progressbar.progress_done()

        logger.logger.info('Done getting emails')

        mail_archiver.update_index()

    if args.mode in ('all', 'calendar'):
        logger.logger.info('Reading calendar entries')
        calendar_entries = backupreader_app.get_calendar_entries()
        calendar_archiver.archive_calendar(calendar_entries)


if __name__ == "__main__":
    run()
