import sqlite3
import dataclasses
from typing import Generator, List

from src.helpers import helpers # type: ignore
from src.logger import config_logger #type: ignore


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
            return helpers.Helper.test_location(
                self.profile_data_location + sqlitedb, 'file')
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

    def get_calendar_entries_from_database(self) -> Generator:
        self.logger.info('Getting calendar entries from database')
        db_connection = self._connect_to_database(self.db_location)
        calendar_table = self._get_calendar_table_name(db_connection)

        if not calendar_table:
            self.logger.warning('No calendar table found, skipping calendar export')
            yield from []
            return

        calendar_entries = self._get_calendar_entries(db_connection, calendar_table)
        for calendar_entry in calendar_entries:
            yield self._get_info_from_calendar(dict(calendar_entry))

    def get_calendar_entries_amount(self) -> int:
        db_connection = self._connect_to_database(self.db_location)
        try:
            calendar_table = self._get_calendar_table_name(db_connection)

            if not calendar_table:
                return 0

            quoted_table = self._quote_identifier(calendar_table)
            if not quoted_table:
                return 0

            try:
                count_result = db_connection.execute(f'SELECT COUNT(*) as count FROM {quoted_table}')
                row = count_result.fetchone()
                return row['count'] if row else 0
            except sqlite3.Error as err:
                self.logger.warning(f'Unable to count calendar entries: {err}')
                return 0
        finally:
            try:
                db_connection.connection.close()
            except Exception:
                pass

    def _get_info_from_calendar(self, calendar_entry: dict) -> dict:
        attendees = self._get_first_present(calendar_entry,
                                            ['Attendees', 'Calendar_Attendees',
                                             'RequiredAttendees', 'OptionalAttendees'])
        return {
            'content_path': self._get_first_present(calendar_entry, ['PathToDataFile', 'DataFilePath']),
            'subject': self._get_first_present(calendar_entry,
                                               ['Calendar_Title', 'Title', 'Subject', 'Summary']),
            'start': self._get_first_present(calendar_entry,
                                             ['StartTime', 'Start', 'StartDate', 'Calendar_StartTime']),
            'end': self._get_first_present(calendar_entry,
                                           ['EndTime', 'End', 'EndDate', 'Calendar_EndTime']),
            'location': self._get_first_present(calendar_entry, ['Location', 'Calendar_Location']),
            'organizer': self._get_first_present(calendar_entry, ['Organizer', 'Calendar_Organizer']),
            'attendees': self._split_list(attendees),
            'id': self._get_first_present(calendar_entry,
                                          ['EntryID', 'RowID', 'CalendarID', 'CalendarEntryID'])
        }

    def _get_first_present(self, calendar_entry: dict, keys):
        for key in keys:
            value = calendar_entry.get(key)
            if value is not None:
                return value
        return None

    def _split_list(self, entries):
        if not entries:
            return []
        if isinstance(entries, list):
            return [entry for entry in entries if entry]
        try:
            return [entry for entry in entries.split(';') if entry]
        except AttributeError:
            return []

    def _get_calendar_table_name(self, db_connection):
        try:
            tables = self._get_tables(db_connection)
        except sqlite3.Error:
            return None

        fallback_name = None
        for table in tables:
            try:
                name = table['name']
            except (KeyError, TypeError, IndexError):
                name = None
            if not name:
                continue
            lower_name = name.lower()
            if lower_name == 'calendar':
                return name
            if 'calendar' in lower_name and not fallback_name:
                fallback_name = name
        return fallback_name

    def _get_calendar_entries(self, db_connection, calendar_table):
        quoted_table = self._quote_identifier(calendar_table)
        if not quoted_table:
            self.logger.warning('Calendar table name contained unsafe characters, skipping')
            return []
        try:
            return db_connection.execute(f'SELECT * FROM {quoted_table}')
        except sqlite3.Error as err:
            self.logger.warning(f'Unable to read calendar entries: {err}')
            return []

    def _quote_identifier(self, identifier: str) -> str:
        """Quote table names sourced from sqlite_schema for safe SQL usage."""
        if not identifier:
            return ''
        cleaned_identifier = ''.join(ch for ch in identifier if ch.isprintable()).strip()
        if not cleaned_identifier:
            return ''
        escaped = cleaned_identifier.replace('"', '""').replace('\x00', '')
        return f'"{escaped}"'
