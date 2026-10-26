import pathlib
import shutil
from datetime import datetime, date
from typing import Dict, List, Optional

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

    def archive_mail(self, mail: Dict, message: bytes) -> None:
        mail_times = self._get_date(mail)
        mail_path = self._get_mail_path(mail, mail_times)
        self._update_mails_info(mail, mail_times)
        self._style_mails(mail, mail_path, message)

    def update_index(self) -> None:
        self.logger.info('Updating index')
        index_location = 'MailArchive/index.html'


        html_start = '<head>\n<link rel="stylesheet" href="./static/css/custom.css">\n</head>\n'
        html_title = '<h2>\nEmails found by the UBF8T346G9 Parser\n</h2>\n'
        html_end = '</body>\n</html>\n'
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
            f.write(message.decode('utf-16-le','ignore'))
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


class CalendarArchiver(config_logger.Logger):
    """Render calendar entries into an HTML page."""

    def __init__(self) -> None:
        self.calendar_location = pathlib.Path('MailArchive/calendar.html')

    def archive_calendar(self, events: List[Dict]) -> None:
        if not events:
            self.logger.warning('No calendar entries found; skipping calendar.html generation')
            return

        self.logger.info('Writing calendar entries to calendar.html')
        sorted_events = sorted(events, key=lambda e: self._to_timestamp(e.get('start')), reverse=True)

        self.logger.debug(
            'Calendar entries discovered: count=%s unique_days=%s examples=%s',
            len(sorted_events),
            len({self._format_day(e.get('start')) for e in sorted_events}),
            [self._event_summary(e) for e in sorted_events[:3]]
        )

        html: List[str] = []
        html.append('<head>\n<link rel="stylesheet" href="./static/css/custom.css">\n</head>\n')
        html.append('<h2>Calendar entries found by the UBF8T346G9 Parser</h2>\n')

        current_day = None
        for event in sorted_events:
            day_label = self._format_day(event.get('start'))
            if day_label != current_day:
                if current_day is not None:
                    html.append('</div>\n')
                current_day = day_label
                html.append(f'<div class="bordermeta">\n<p><b>{day_label}</b></p>\n</div>\n')
                html.append('<div class="bordermail">\n')

            html.append(self._render_event(event))
        if sorted_events:
            html.append('</div>\n')

        self.calendar_location.parent.mkdir(parents=True, exist_ok=True)

        with self.calendar_location.open('w') as f:
            f.writelines(html)

    def export_ics(self, events: List[Dict], output_path: str) -> None:
        try:
            import icalendar
        except ImportError:
            self.logger.warning('icalendar package not installed; skipping ICS export')
            return

        events_sorted = sorted(events, key=lambda e: self._to_timestamp(e.get('start')), reverse=True)

        output = pathlib.Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        cal = icalendar.Calendar()
        cal.add('prodid', '-//UBF8T346G9 Parser//ICS Export//EN')
        cal.add('version', '2.0')
        timezones = {}

        for event in events_sorted:
            dt_start = self._coerce_to_datetime(event.get('start'))
            dt_end = self._coerce_to_datetime(event.get('end'))
            if not dt_start or not dt_end:
                continue

            vevent = icalendar.Event()
            vevent.add('uid', event.get('uid') or str(event.get('id') or id(event)))
            vevent.add('dtstart', dt_start.date() if event.get('all_day') else dt_start)
            vevent.add('dtend', dt_end.date() if event.get('all_day') else dt_end)
            if event.get('rrule'):
                vevent.add('rrule', event['rrule'])
                zone = dt_start.tzinfo
                if getattr(zone, 'key', None):
                    timezones[zone.key] = zone
            for excluded in event.get('exdates', []):
                vevent.add('exdate', excluded)
            if isinstance(event.get('recurrence_id'), date):
                vevent.add('recurrence-id', event['recurrence_id'])
            if event.get('is_cancelled'):
                vevent.add('status', 'CANCELLED')
            if event.get('subject'):
                vevent.add('summary', event.get('subject'))
            body_text = self._strip_tags((event.get('description') or '').strip()) or ''
            if body_text:
                # Normalize to single-line with escaped newlines
                import html
                body_text = html.unescape(body_text).strip()
                # Keep actual newline characters; icalendar will escape them as \n (single slash)
                body_text = body_text.replace('\r\n', '\n').replace('\r', '\n')
                import re
                body_text = re.sub(r'\n{3,}', '\n\n', body_text)
                vevent.add('description', body_text)
            # Add HTML alternative description as single-line text/html
            alt_html = (event.get('description') or '').strip()
            if alt_html:
                import re
                alt_html = alt_html.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
                alt_html = re.sub(r'\s{2,}', ' ', alt_html).strip()
                vevent.add('X-ALT-DESC', alt_html, parameters={'FMTTYPE': 'text/html'})
            if event.get('location'):
                vevent.add('location', event.get('location'))
            if event.get('organizer'):
                email = self._first_email(event.get('organizer'))
                if email:
                    vevent.add('organizer', f'mailto:{email}')
            if event.get('attendees'):
                for att in event.get('attendees'):
                    email = self._first_email(att)
                    if email:
                        vevent.add('attendee', f'mailto:{email}', parameters={'cn': att.split("<")[0].strip() or email})
            if event.get('online_join_link'):
                vevent.add('url', event.get('online_join_link'))
            cal.add_component(vevent)

        for zone in timezones.values():
            cal.add_component(icalendar.Timezone.from_tzinfo(zone))

        with output.open('wb') as f:
            f.write(cal.to_ical())
        self.logger.info(f'Wrote ICS calendar to {output}')

    def _render_event(self, event: Dict) -> str:
        raw_body = self._read_body(event.get('content_path'))
        subject = event.get('subject') or self._extract_subject(raw_body) or event.get('fallback_subject') or 'Untitled event'
        location = event.get('location') or 'Unspecified location'

        emails_in_body = self._extract_emails(raw_body)
        organizer = event.get('organizer') or (emails_in_body[0] if emails_in_body else None) or 'Unknown organizer'
        attendees_list = event.get('attendees') or emails_in_body[1:] or []
        attendees = ', '.join(attendees_list) or 'No attendees listed'
        description = event.get('description') or ''
        body = (raw_body or description).strip()

        all_day = 'Yes' if event.get('all_day') else 'No'
        busy_status = event.get('busy_status') or 'Unspecified'
        is_recurring = 'Yes' if event.get('is_recurring') else 'No'
        is_cancelled = 'Yes' if event.get('is_cancelled') else 'No'
        attendee_count = event.get('attendee_count')
        attendee_count_text = attendee_count if attendee_count is not None else 'Unknown'
        online_link = event.get('online_join_link')
        calendar_owner = event.get('calendar_owner') or 'Unknown'
        uid = event.get('uid') or 'Unknown'
        folder_id = event.get('folder_id') or 'Unknown'
        account_uid = event.get('account_uid') or 'Unknown'
        category_id = event.get('category_id') or 'Unknown'

        meta_parts = [
            '<div class="bordermeta">\n',
            f'<p><b>{subject}</b></p>\n',
            f'<p>Organizer: {organizer}</p>\n',
            f'<p>When: {self._format_time_range(event.get("start"), event.get("end"))}</p>\n',
            f'<p>Location: {location}</p>\n',
            f'<p>Attendees: {attendees}</p>\n',
            f'<p>All day: {all_day} | Busy status: {busy_status} | Recurring: {is_recurring} | Cancelled: {is_cancelled}</p>\n',
            f'<p>Attendee count: {attendee_count_text} | Calendar owner: {calendar_owner}</p>\n',
            f'<p>UID: {uid} | FolderID: {folder_id} | AccountUID: {account_uid} | CategoryID: {category_id}</p>\n',
        ]
        if online_link:
            meta_parts.append(f"<p>Online link: <a href='{online_link}'>{online_link}</a></p>\n")
        meta_parts.append(f'<p>Event ID: {event.get("id")}</p>\n')
        meta_parts.append('</div>\n')

        return ''.join(meta_parts) + f'<div class="bordermail">\n{body}\n</div>\n'

    def _format_time_range(self, start: Optional[object], end: Optional[object]) -> str:
        start_text = self._format_datetime(start) or 'Unknown start'
        end_text = self._format_datetime(end) or 'Unknown end'
        if start_text and end_text:
            return f'{start_text} — {end_text}'
        return start_text or end_text

    def _format_day(self, value: Optional[object]) -> str:
        formatted = self._format_datetime(value, day_only=True)
        return formatted or 'Unknown date'

    def _format_datetime(self, value: Optional[object], day_only: bool=False) -> Optional[str]:
        if value is None:
            return None
        try:
            dt = self._coerce_to_datetime(value)
        except Exception:
            try:
                dt = datetime.fromisoformat(str(value))
            except Exception:
                return str(value)

        if day_only:
            return dt.strftime('%Y-%m-%d')
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    def _read_body(self, content_path: Optional[str]) -> str:
        if not content_path:
            return ''

        try:
            with open(content_path, 'rb') as f:
                raw = f.read()
                try:
                    return raw.decode('utf-16-le', 'ignore')
                except Exception:
                    return raw.decode('utf-8', 'ignore')
        except FileNotFoundError:
            self.logger.debug(f'Missing calendar content file: {content_path}')
            return ''

    def _event_summary(self, event: Dict) -> str:
        return '{subject} ({time}) @ {location}'.format(
            subject=event.get('subject') or 'Untitled',
            time=self._format_time_range(event.get('start'), event.get('end')),
            location=event.get('location') or 'n/a'
        )

    def _extract_subject(self, body: str) -> Optional[str]:
        if not body:
            return None
        lowered = body.lower()
        start = lowered.find('<title>')
        if start != -1:
            end = lowered.find('</title>', start)
            if end != -1:
                return body[start+7:end].strip()

        # Headings or bold text as fallback
        for marker in ['<h1', '<h2', '<h3', 'font-weight:700', 'font-weight:bold']:
            idx = lowered.find(marker)
            if idx != -1:
                segment = body[idx:idx+200]
                text = self._strip_tags(segment)
                if text:
                    return text[:120].strip()
        # Fallback: first line of text
        text = self._strip_tags(body).strip()
        return text.splitlines()[0][:120].strip() if text else None

    def _extract_emails(self, body: str) -> List[str]:
        if not body:
            return []
        import re
        emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}', body)
        seen = set()
        deduped = []
        for e in emails:
            if e not in seen:
                seen.add(e)
                deduped.append(e)
    def _strip_tags(self, html: str) -> str:
        import re
        return re.sub(r'<[^>]+>', '', html)


    def _extract_emails(self, body: str) -> List[str]:
        if not body:
            return []
        import re
        emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}', body)
        seen = set()
        deduped = []
        for e in emails:
            if e not in seen:
                seen.add(e)
                deduped.append(e)
        return deduped

    def _first_email(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        import re
        match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}', text)
        return match.group(0) if match else None

    def _coerce_to_datetime(self, value: object) -> datetime:
        """Normalize datetime/date/timestamp-like values to datetime."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            # treat all-day dates as midnight
            return datetime.combine(value, datetime.min.time())
        # Numeric timestamp
        ts = float(value)
        dt = datetime.fromtimestamp(ts)
        # If timestamp looks off, try interpreting as minutes since 1601-01-01.
        if dt.year < 1980 or dt.year > 2100:
            dt = datetime.fromtimestamp(ts * 60 - 11644473600)
        return dt

    def _to_timestamp(self, value: Optional[object]) -> float:
        if value is None:
            return 0.0
        try:
            dt = self._coerce_to_datetime(value)
            return dt.timestamp()
        except Exception:
            return 0.0
