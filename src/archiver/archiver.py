import pathlib
import shutil
from datetime import datetime
import html
from typing import Dict, List, Optional

# Archiver configuration constants
STYLESHEET_PATH = "./static/css/custom.css"
UNIX_Y2K_EPOCH = 946684800  # Unix timestamp for 2000-01-01 (used to spot Mac absolute times)
MAC_EPOCH_OFFSET = 978307200  # Seconds between Unix epoch and Mac absolute time (2001-01-01)
MILLISECOND_TIMESTAMP_THRESHOLD = 1e12  # Values above this are assumed to be millisecond timestamps
MESSAGE_ENCODING = 'utf-16-le'

from src.helpers import helpers #type: ignore
from src.logger import config_logger #type: ignore

import locale
try:
    locale.setlocale(locale.LC_ALL, 'da_DK.utf8')
except:
    pass

class MailArchiver(config_logger.Logger):
    """Archive email
    """

    def __init__(self) -> None:
        self.mailsdir = 'MailArchive/Mails'
        self._check_mailsdir(self.mailsdir)
        self.mails_info = {}
        self.calendar_entries: List[Dict] = []
        self.stylesheet_path = STYLESHEET_PATH

    def archive_mail(self, mail: Dict, message: bytes) -> None:
        mail_times = self._get_date(mail)
        mail_path = self._get_mail_path(mail, mail_times)
        self._update_mails_info(mail, mail_times)
        self._style_mails(mail, mail_path, message)

    def update_index(self) -> None:
        self.logger.info('Updating index')
        index_location = 'MailArchive/index.html'

        html_start, html_title, html_end = self._get_html_wrapper(
            'Emails found by the UBF8T346G9 Parser')
        html_year = '<details>\n<summary>{year}</summary>\n{months}\n</details>\n'
        html_month = '<details>\n<summary>{month}</summary>\n{days}\n</details>\n'
        html_day = '<details>\n<summary>{day}</summary>\n{topics}\n</details>\n'
        html_topic_entry = '''<p>\n<a href='{path}'>{subject}</a> - id: {id}\n</p>\n'''

        years_to_write = []
        for year in sorted(self.mails_info.keys()):

            months_for_the_year = []
            for month in sorted(self.mails_info[year].keys()):

                days_for_the_month = []
                for day in sorted(self.mails_info[year][month].keys()):

                    topics_for_the_day = []
                    for topic in self.mails_info[year][month][day]:
                        topics_for_the_day.append(html_topic_entry.format(
                            path=topic.get('path'),
                            subject=topic.get('subject'),
                            id=topic.get('id'),
                        ))

                    days_for_the_month.append(
                        html_day.format(day=day, topics=''.join(topics_for_the_day)))

                months_for_the_year.append(
                    html_month.format(month=datetime.strptime(month,'%m').strftime('%B'), days=''.join(days_for_the_month)))

            years_to_write.append(
                html_year.format(year=year, months=''.join(months_for_the_year)))

        index_content = html_start + html_title + ''.join(years_to_write) + html_end

        with open(index_location, 'w') as f:
            f.write(index_content)

    def archive_calendar_entry(self, calendar_entry: Dict, message: bytes) -> None:
        try:
            content = message.decode(MESSAGE_ENCODING, 'ignore')
        except (UnicodeDecodeError, LookupError):
            content = ''

        self.calendar_entries.append({
            'id': calendar_entry.get('id'),
            'subject': calendar_entry.get('subject') or 'No subject',
            'location': calendar_entry.get('location') or 'No location',
            'organizer': calendar_entry.get('organizer') or 'Unknown organizer',
            'attendees': calendar_entry.get('attendees') or [],
            'start': self._get_event_datetime(calendar_entry.get('start')),
            'end': self._get_event_datetime(calendar_entry.get('end')),
            'raw_start': calendar_entry.get('start'),
            'raw_end': calendar_entry.get('end'),
            'content': content
        })

    def update_calendar(self) -> None:
        if not self.calendar_entries:
            self.logger.info('No calendar entries found, skipping calendar.html generation')
            return

        calendar_location = 'MailArchive/calendar.html'
        pathlib.Path(calendar_location).parent.mkdir(parents=True, exist_ok=True)

        html_start, html_title, html_end = self._get_html_wrapper(
            'Calendar entries found by the UBF8T346G9 Parser')

        calendar_entries = sorted(self.calendar_entries, key=self._calendar_sort_key)
        rendered_entries = [self._render_calendar_entry(entry) for entry in calendar_entries]

        with open(calendar_location, 'w') as f:
            f.write(html_start + html_title + ''.join(rendered_entries) + html_end)

    def _get_html_wrapper(self, title: str):
        html_start = (
            '<!DOCTYPE html>\n'
            '<html>\n'
            '<head>\n'
            f'<link rel="stylesheet" href="{self.stylesheet_path}">\n'
            '</head>\n'
            '<body>\n'
        )
        html_title = f'<h2>\n{title}\n</h2>\n'
        html_end = '</body>\n</html>\n'
        return html_start, html_title, html_end

    def _render_calendar_entry(self, entry: Dict) -> str:
        attendees = entry.get('attendees') or []
        attendees_text = ' | '.join([html.escape(attendee) for attendee in attendees]) if attendees else 'None'

        meta_data = (
            "\n<div class=\"bordermeta\">\n"
            "<p>\nSubject: <b>{subject}</b>\n</p>\n"
            "<p>\nOrganizer: {organizer}\n</p>\n"
            "<p>\nLocation: {location}\n</p>\n"
            "<p>\nAttendees: {attendees}\n</p>\n"
            "<p>\nStart: {start}\n</p>\n"
            "<p>\nEnd: {end}\n</p>\n"
            "</div>\n"
        )

        meta_data = meta_data.format(
            subject=html.escape(entry.get('subject') or ''),
            organizer=html.escape(entry.get('organizer') or ''),
            location=html.escape(entry.get('location') or ''),
            attendees=attendees_text,
            start=self._format_event_datetime(entry.get('start'), entry.get('raw_start')),
            end=self._format_event_datetime(entry.get('end'), entry.get('raw_end')),
        )

        safe_content = html.escape(entry.get('content') or '')
        return meta_data + '\n<div class="bordermail">\n' + safe_content + '\n</div>\n<hr>\n'

    def _calendar_sort_key(self, entry: Dict):
        datetime_value = entry.get('start')
        if isinstance(datetime_value, datetime):
            return datetime_value
        return datetime.min

    def _get_event_datetime(self, value: Optional[object]) -> Optional[datetime]:
        """Normalize event timestamps from Outlook data.

        Handles millisecond-based Unix timestamps as well as Mac absolute time
        values (seconds since 2001-01-01) by converting them into standard Unix
        timestamps for display. Timestamps earlier than UNIX_Y2K_EPOCH are
        treated as Mac absolute time.
        """
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None

        if timestamp > MILLISECOND_TIMESTAMP_THRESHOLD:
            # Convert millisecond epoch values to seconds.
            timestamp = timestamp / 1000
        elif timestamp < UNIX_Y2K_EPOCH:
            # Adjust Mac absolute time (seconds since 2001-01-01) to Unix epoch.
            adjusted_timestamp = timestamp + MAC_EPOCH_OFFSET
            if adjusted_timestamp > UNIX_Y2K_EPOCH:
                timestamp = adjusted_timestamp

        try:
            return datetime.fromtimestamp(timestamp)
        except (OverflowError, OSError, ValueError):
            return None

    def _format_event_datetime(self, datetime_value: Optional[datetime], raw_value: Optional[object]) -> str:
        if isinstance(datetime_value, datetime):
            return datetime_value.strftime("%Y-%m-%d %H:%M:%S")
        if raw_value is None:
            return 'Unknown'
        return html.escape(str(raw_value))

    def _update_mails_info(self, mail, mail_times):
        year = mail_times.get('year')
        month = mail_times.get('month')
        day = mail_times.get('day')
        mailid = mail.get('id')

        mail_info = {
            'path': 'Mails/{year}/{month}/{day}/{mailid}.html'.format(
                year=year,
                month=month,
                day=day,
                mailid=mailid
            ),
            'subject': mail.get('subject'),
            'id': mailid
        }

        if not self.mails_info.get(year):
            self.mails_info[year] = {}

        if not self.mails_info[year].get(month):
            self.mails_info[year][month] = {}

        if not self.mails_info[year][month].get(day):
            self.mails_info[year][month][day] = [mail_info]
        elif mail_info not in self.mails_info[year][month][day]:
            self.mails_info[year][month][day].append(mail_info)


    def _style_mails(self, mail: Dict, mail_path: str, message: bytes):

        with helpers.Helper.open_file(mail_path) as f:
            f.write('<head>\n<link rel="stylesheet" href="../../../../static/css/custom.css">\n</head>\n')
            self._write_meta_data(mail, f)
            f.write('\n<div class="bordermail">\n')
            f.write(message.decode(MESSAGE_ENCODING,'ignore'))
            f.write('\n</div>\n')

    def _write_meta_data(self, mail: Dict, mail_file):
        meta_data = '''\n<div class="bordermeta">\n<p>\nSubject: <b>{subject}</b>\n</p>\n<p>\nFrom: {sender}\n</p>\n<p>\nTo: {recipients}\n</p>\n<p>\nCC: {cc}\n</p>\n<p>\nDate: {date}\n</p>\n</div>\n'''
        sendertext = self._get_sender(mail)
        recipientstext = self._get_recipients(mail)
        timetext = self._get_time(mail)

        meta_data = meta_data.format(
            subject=mail.get('subject'),
            sender=sendertext,
            recipients=' | '.join(recipientstext),
            cc=mail.get('cc'),
            date=timetext
        )

        mail_file.write(meta_data)

    def _get_time(self, mail):
        time = self._get_date(mail)
        timetext = '{hours}:{minutes}:{seconds} {day}/{month}/{year}'.format(
            year=time.get('year'),
            month=time.get('month'),
            day=time.get('day'),
            hours=time.get('hours'),
            minutes=time.get('minutes'),
            seconds=time.get('seconds'),
        )
        return timetext

    def _get_sender(self, mail):
        sender = mail.get('sender')
        sendertext = '<b>{name}</b> - <b>{email}</b>'.format(
            email=sender.get('email'), #type: ignore
            name=sender.get('name') #type: ignore
        )
        return sendertext

    def _get_recipients(self, mail):
        recipients = mail.get('recipients')
        recipientstext = []
        if recipients != [None]:
            for recipient in recipients: #type: ignore
                recipientstext.append('<b>{name}</b> - <b>{email}</b>'.format(
                    email=recipient.get('email'), #type: ignore
                    name=recipient.get('name') #type: ignore
                ))
        return recipientstext

    def _get_date(self, mail: Dict) -> Dict:
        mail_date = datetime.fromtimestamp(mail.get('time'))
        return {
            'year': mail_date.strftime("%Y"),
            'month': mail_date.strftime("%m"),
            'day': mail_date.strftime("%d"),
            'hours': mail_date.strftime("%H"),
            'minutes': mail_date.strftime("%M"),
            'seconds': mail_date.strftime("%S"),
        }

    def _get_mail_path(self, mail: Dict, mail_times: Dict) -> str:
        mail_dir = self._create_mail_dirs(mail_times)
        return '{}/{}.html'.format(mail_dir, mail.get('id'))

    def _create_mail_dirs(self, mail_times: Dict) -> str:
        mail_dir = '{mailsdir}/{year}/{month}/{day}'.format(
            mailsdir=self.mailsdir,
            year=mail_times.get('year'),
            month=mail_times.get('month'),
            day=mail_times.get('day')
        )

        pathlib.Path(mail_dir).mkdir(parents=True, exist_ok=True)
        return mail_dir

    def _check_mailsdir(self, mailsdir: str):
        mails_dir = pathlib.Path(mailsdir)
        if mails_dir.is_dir():
            userinput = input('The Mails directory already exists, do you want '
                              'to start over? [Y/n]: ')

            if 'n' == userinput.lower() or 'no' == userinput.lower():
                self.logger.info('Exiting.')
                exit(0)
            else:
                self.logger.info(f'Removing {mails_dir}')
                shutil.rmtree(mails_dir)
