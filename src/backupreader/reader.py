import sqlite3
import pathlib
import dataclasses
import sys
from typing import Generator, List, Optional
from datetime import datetime

from src.helpers import helpers # type: ignore
from src.logger import config_logger #type: ignore
from src.recurrence import link_overrides, recurrence_fields

def _first_match(row: dict, candidates: List[str]):
    """Return first present value from row based on candidate column names."""
    for key in candidates:
        if key in row and row.get(key) not in (None, ''):
            return row.get(key)
    return None

# Ensure pyolk modules are importable
PYOLK_PATH = pathlib.Path(__file__).resolve().parents[1] / 'pyolk'
if str(PYOLK_PATH) not in sys.path:
    sys.path.insert(0, str(PYOLK_PATH))

# pyolk imports (module-based)
import pyolk as pyolk_module


class _CalendarPyOLKReader(pyolk_module.PyOLKReader):
    """PyOLKReader variant that only loads calendar events to avoid bad mail blobs."""

    def load_archive(self):
        # Only load calendar events; skip mail/other tables that might contain corrupted blobs.
        t, q = self._calendar_event_query()
        self.Events = self._get_items(t, q, pyolk_module.OlkEvent)

@dataclasses.dataclass
class BackupReader(config_logger.Logger):
    """Read data from Outlook 2016 Backup folder.

    Attributes:
      backup_location: A string of backup folder location.
      profile_data_location: A string of data folder location based on user.
    """

    profile_data_location: str
    filter_hidden = '/.'

    @property
    def db_location(self):
        sqlitedb = 'Outlook.sqlite'
        try:
            base_path = pathlib.Path(self.profile_data_location)
            return helpers.Helper.test_location(
                str(base_path / sqlitedb), 'file')
        except FileNotFoundError:
            self.logger.warning(f'Missing {sqlitedb}, is the database missing?')
            raise FileNotFoundError

    def get_mails_from_database(self) -> Generator:
        self.logger.info('Getting emails from database')
        db_connection = self._connect_to_database(self.db_location)
        mails = self._get_mails(db_connection)
        for mail in mails:
            yield self._get_info_from_email(dict(mail))

    def get_mails_amount(self) -> int:
        db_connection = self._connect_to_database(self.db_location)
        mails = self._get_mails(db_connection)
        return len(list(mails))

    def get_calendar_entries(self, folder_ids: Optional[List[int]]=None) -> List[dict]:
        """Extract calendar entries using pyolk's OLK parser for accuracy."""
        self.logger.info('Parsing calendar entries with pyolk')
        olk_reader = _CalendarPyOLKReader(path=self.profile_data_location)
        events = []
        for event in olk_reader.Events.values():
            mapped = self._map_pyolk_event(event)
            events.append(mapped)
        link_overrides(events)
        return [event for event in events
                if not folder_ids or event.get('folder_id') in folder_ids]

    def get_calendar_folders(self) -> List[dict]:
        """Return calendar folders (FolderClass == 2) with IDs and account UIDs."""
        cur = self._connect_to_database(self.db_location)
        rows = cur.execute(
            "SELECT Record_RecordID AS id, Folder_Name AS name, Record_AccountUID AS account_uid "
            "FROM Folders WHERE Folder_FolderClass = 2"
        ).fetchall()
        return [dict(r) for r in rows]

    def _get_info_from_email(self, mail: dict) -> dict:
        return {
            'content_path' : mail.get('PathToDataFile'),
            'subject' : mail.get('Message_ThreadTopic'),
            'time' : mail.get('Message_TimeReceived'),
            'sender' : {'email': mail.get('Message_SenderAddressList'),
                        'name': mail.get('Message_SenderList')},
            'recipients' : self._merge_recipients(
                mail.get('Message_ToRecipientAddressList'),
                mail.get('Message_RecipientList')),
            'cc' : mail.get('Message_CCRecipientAddressList'),
            'type' : mail.get('Message_type'),
            'id': mail.get('Threads_ThreadID'),
        }

    def _merge_recipients(self, emails: str, names: str) -> List:
        try:
            emails_split = emails.split(';')
            names_split = names.split(';')
        except AttributeError:
            return [None]

        recipients = []
        for email, name in zip(emails_split, names_split):
            recipients.append({
                'email': email,
                'name': name
            })

        return recipients

    def _connect_to_database(self, db_location):
        db_connection = sqlite3.connect(db_location)
        db_connection.row_factory = sqlite3.Row
        return db_connection.cursor()

    def _get_mails(self, db_connection):
        return db_connection.execute('SELECT * FROM Mail')

    def _get_tables(self, db_connection):
        return db_connection.execute("SELECT * FROM sqlite_schema WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ")

    def _find_calendar_table(self, db_connection):
        tables = self._get_tables(db_connection)
        for table in tables:
            if isinstance(table, sqlite3.Row):
                name = table['name']
            else:
                name = table[1] if len(table) > 1 else table[0]
            if name and 'calendar' in name.lower():
                return name
            if name and 'event' in name.lower():
                return name
        return None

    def _get_info_from_calendar(self, row: dict, columns: List[str]) -> dict:
        subject = _first_match(row, [
            'Subject', 'Title', 'Summary', 'Calendar_Summary',
            'Calendar_Subject', 'AppointmentTitle', 'Topic', 'Name'
        ])
        start_time = self._convert_outlook_minutes(row.get('Calendar_StartDateUTC'))
        if start_time is None:
            start_time = self._normalize_timestamp(_first_match(row, [
                'StartTimeUTC', 'StartDateUTC', 'StartAbsoluteDate',
                'StartTime', 'StartDate', 'Calendar_StartTime', 'Start',
                'StartDateTime', 'DateStart', 'DateTimeUTC', 'TimeStart'
            ]))

        end_time = self._convert_outlook_minutes(row.get('Calendar_EndDateUTC'))
        if end_time is None:
            end_time = self._normalize_timestamp(_first_match(row, [
                'EndTimeUTC', 'EndDateUTC', 'EndAbsoluteDate',
                'EndTime', 'EndDate', 'Calendar_EndTime', 'End',
                'EndDateTime', 'DateEnd', 'TimeEnd'
            ]))
        location = _first_match(row, ['Location', 'Calendar_Location', 'Where', 'Place'])
        organizer = _first_match(row, ['Organizer', 'OrganizerName', 'Owner', 'Creator', 'From'])
        attendees_raw = _first_match(row, [
            'Attendees', 'AttendeeList', 'ToRecipientAddressList',
            'RequiredAttendees', 'OptionalAttendees', 'Participants'
        ])
        description = _first_match(row, ['Body', 'Notes', 'Description', 'Text', 'Content'])
        content_path_raw = _first_match(row, [
            'PathToDataFile', 'PathToDataFile_W', 'DataFilePath', 'ContentPath'
        ])
        content_path = self._resolve_content_path(content_path_raw)
        record_id = _first_match(row, ['RecordID', 'ItemID', 'ID', 'Uid', 'CalendarID', 'AppointmentID'])

        attendees = []
        if isinstance(attendees_raw, str):
            attendees = [att.strip() for att in attendees_raw.split(';') if att.strip()]
        elif isinstance(attendees_raw, list):
            attendees = attendees_raw

        return {
            'subject': subject,
            'start': start_time,
            'end': end_time,
            'location': location,
            'organizer': organizer,
            'attendees': attendees,
            'description': description,
            'content_path': content_path,
            'id': record_id,
            'fallback_subject': pathlib.Path(content_path_raw).stem if content_path_raw else None,
            'raw_columns': columns,
            'raw': row,
        }

    def _normalize_timestamp(self, value):
        if value is None:
            return None

        # ISO formatted string
        if isinstance(value, str) and any(c in value for c in ['-', 'T', ':']):
            try:
                return datetime.fromisoformat(value).replace(tzinfo=None).timestamp()
            except Exception:
                pass

        # Raw bytes? Decode best-effort
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode('utf-8')
            except Exception:
                value = value.decode('utf-16-le', 'ignore')

        try:
            num = float(value)
        except Exception:
            return None

        # .NET ticks (100ns since 0001-01-01)
        if num > 1e14:
            num = num / 1e7 - 62135596800
        # Milliseconds
        elif num > 1e12:
            num = num / 1000
        # Minutes since 1601-01-01 (Exchange FILETIME minutes) -> convert to unix epoch seconds
        elif 1e6 < num < 5e8:
            num = num * 60 - 11644473600
        # Mac absolute time (seconds since 2001-01-01)
        elif 0 < num < 978307200:
            num = num + 978307200

        return num

    def _convert_outlook_minutes(self, value):
        """Outlook for Mac stores Calendar_*DateUTC as minutes since 1601-01-01."""
        if value is None:
            return None
        try:
            minutes = float(value)
        except Exception:
            return None
        # sanity: ignore clearly invalid minute ranges
        if minutes < 1e5 or minutes > 1e9:
            return None
        # convert minutes to Unix epoch seconds
        return minutes * 60 - 11644473600

    def _resolve_content_path(self, path: str) -> str:
        if not path:
            return ''
        path_obj = pathlib.Path(path)
        if path_obj.is_absolute() or path_obj.exists():
            return str(path_obj)
        return str(pathlib.Path(self.profile_data_location) / path_obj)

    def _map_pyolk_event(self, event):
        # pyolk already decodes OLK binaries and Outlook sqlite timestamps
        start = event.StartDateUTC
        end = event.EndDateUTC
        organizer = None
        if getattr(event, 'Organizer', None):
            organizer = f"{event.Organizer.Name} <{event.Organizer.Address}>"
        attendees = []
        for a in getattr(event, 'Attendees', []):
            attendees.append(f"{a.Name} <{a.Address}>")
        content_path_raw = getattr(event, 'PathToDataFile', None)
        # Prefer the already-parsed Body from pyolk; do not fall back to raw OLK file to avoid gibberish.
        content_path = None
        return {
            'subject': getattr(event, 'Subject', None),
            'start': start,
            'end': end,
            'location': getattr(event, 'Location', None),
            'organizer': organizer,
            'attendees': attendees,
            'description': getattr(event, 'Body', None),
            'content_path': content_path,
            'id': getattr(event, 'RecordID', None),
            'fallback_subject': getattr(event, 'Topic', None),
            'folder_id': getattr(event, 'FolderID', None),
            'account_uid': getattr(event, 'AccountUID', None),
            'category_id': getattr(event, 'CategoryID', None),
            'all_day': getattr(event, 'AllDayEvent', None),
            'busy_status': getattr(event, 'BusyStatus', None),
            'is_cancelled': getattr(event, 'IsCancelled', None),
            'is_recurring': getattr(event, 'IsRecurring', None),
            'master_id': getattr(event, 'MasterRecordID', None),
            'recurrence_id': getattr(event, 'RecurrenceID', None),
            'attendee_count': getattr(event, 'AttendeeCount', None),
            'online_join_link': getattr(event, 'ConferenceHTTPJoinLink', None),
            'calendar_owner': getattr(event, 'CalendarOwnerName', None),
            'uid': getattr(event, 'ExchangeID', None) or f'outlook-{event.AccountUID}-{event.RecordID}',
            'raw_columns': [],
            'raw': {},
            **recurrence_fields(event),
        }
