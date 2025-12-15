#!/usr/bin/env python
from src.backupreader import reader
from src.olk15parser import parser
from src.archiver import archiver
from src.helpers import helpers
from src.helpers import progress
from src.logger import config_logger

logger = config_logger.Logger()

if __name__ == "__main__":
    profile_data_location = helpers.Helper.get_location()
    backupreader_app = reader.BackupReader(profile_data_location)
    olk15parser_app = parser.OLK15Parser()
    archiver_app = archiver.MailArchiver()

    mails_amount = backupreader_app.get_mails_amount()
    progressbar = progress.ProgressBar(mails_amount)
    calendar_entries_amount = backupreader_app.get_calendar_entries_amount()
    calendar_progressbar = progress.ProgressBar(calendar_entries_amount) if calendar_entries_amount > 0 else None

    mails = backupreader_app.get_mails_from_database()

    logger.logger.info('Getting email content and writing to files')
    for mail in mails:
        progressbar.update()
        mail_path = profile_data_location + mail.get('content_path')
        message = olk15parser_app.get_content(mail_path, mail.get('subject'))
        archiver_app.archive_mail(mail, message)

    progressbar.progress_done()

    logger.logger.info('Done getting emails')

    if calendar_entries_amount > 0:
        logger.logger.info('Getting calendar content and writing to calendar.html')
        calendar_entries = backupreader_app.get_calendar_entries_from_database()

        for calendar_entry in calendar_entries:
            if calendar_progressbar:
                calendar_progressbar.update()

            content_path = calendar_entry.get('content_path')
            calendar_message = b''
            calendar_path = ''

            if content_path:
                calendar_path = profile_data_location + content_path
                try:
                    calendar_message = olk15parser_app.get_content(
                        calendar_path, calendar_entry.get('subject') or '')
                except FileNotFoundError:
                    logger.logger.warning(f'Missing calendar content file: {calendar_path}')

            archiver_app.archive_calendar_entry(calendar_entry, calendar_message)

        if calendar_progressbar:
            calendar_progressbar.progress_done()
    else:
        logger.logger.info('No calendar entries found')

    archiver_app.update_calendar()
    archiver_app.update_index()
