from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from dateutil.rrule import rrulestr
from icalendar import Calendar

from parser_app import _filter_future
from src.archiver.archiver import CalendarArchiver
from src.backupreader.reader import BackupReader
from src.recurrence import link_overrides, recurrence_fields


ZONE = ZoneInfo('Europe/Amsterdam')
CUTOFF = datetime(2026, 10, 26, tzinfo=ZONE)


def source_event(**changes):
    event = SimpleNamespace(
        StartDateUTC=datetime(2026, 10, 5, 8, tzinfo=timezone.utc),
        EndDateUTC=datetime(2026, 10, 5, 9, tzinfo=timezone.utc),
        Timezone=SimpleNamespace(TZID='Europe/Amsterdam'),
        RRule=SimpleNamespace(
            RecurrenceType='Weekly', Freq='Weekly', Interval=1, Day='MO',
            MonthDay=None, SetPos=None, EndType='None', Occurrences=10,
            Until=date(4500, 12, 31), ExceptionDates=[date(2026, 10, 5)],
            RecurrenceDates=[date(2026, 10, 5), date(2026, 10, 12)],
        ),
        RecordID=1, AccountUID=1, FolderID=119, MasterRecordID=0,
        RecurrenceID=0, ExchangeID='series@example.test',
        Subject='Weekly planning', AllDayEvent=False, IsRecurring=True,
    )
    for name, value in changes.items():
        setattr(event, name, value)
    return event


def mapped_event(**changes):
    return BackupReader('.')._map_pyolk_event(source_event(**changes))


def write_calendar(tmp_path, events):
    output = tmp_path / 'calendar.ics'
    CalendarArchiver().export_ics(events, str(output))
    calendar = Calendar.from_ical(output.read_bytes())
    assert all(not component.errors for component in calendar.walk())
    return calendar


def occurrences(component):
    start = component.decoded('dtstart')
    if not isinstance(start, datetime):
        start = datetime.combine(start, datetime.min.time())
    result = rrulestr(component['rrule'].to_ical().decode(), dtstart=start, forceset=True)
    excluded = component.get('exdate', [])
    if not isinstance(excluded, list):
        excluded = [excluded]
    for entry in excluded:
        for item in entry.dts:
            value = item.dt
            if not isinstance(value, datetime):
                value = datetime.combine(value, datetime.min.time())
            result.exdate(value)
    return result


def test_series_survives_future_filter_and_dst_round_trip(tmp_path):
    event = mapped_event()
    assert _filter_future([event], CUTOFF) == [event]
    calendar = write_calendar(tmp_path, [event])
    component = calendar.walk('VEVENT')[0]
    next_start = occurrences(component).after(CUTOFF)
    assert next_start == datetime(2026, 10, 26, 10, tzinfo=ZONE)
    assert next_start.astimezone(timezone.utc).hour == 9
    assert component.decoded('dtstart').hour == 10
    assert len(calendar.walk('VTIMEZONE')) == 1
    assert 'UNTIL' not in component['rrule']
    assert 'COUNT' not in component['rrule']


def test_deleted_occurrence_is_not_exported_as_an_additional_date(tmp_path):
    calendar = write_calendar(tmp_path, [mapped_event()])
    component = calendar.walk('VEVENT')[0]
    assert 'RDATE' not in component
    assert occurrences(component).after(datetime(2026, 10, 5, tzinfo=ZONE)) == datetime(2026, 10, 12, 10, tzinfo=ZONE)


@pytest.mark.parametrize('end_type,until,count,retained', [
    ('ByDate', date(2026, 10, 19), 10, False),
    ('ByDate', date(2026, 10, 26), 10, True),
    ('AfterCount', date(4500, 12, 31), 3, False),
    ('AfterCount', date(4500, 12, 31), 4, True),
])
def test_bounded_series_uses_actual_recurrence_end(end_type, until, count, retained):
    source = source_event()
    source.RRule.EndType = end_type
    source.RRule.Until = until
    source.RRule.Occurrences = count
    event = BackupReader('.')._map_pyolk_event(source)
    assert bool(_filter_future([event], CUTOFF)) is retained
    assert not ('until' in event['rrule'] and 'count' in event['rrule'])


def test_expired_series_with_final_occurrence_deleted_is_removed():
    source = source_event()
    source.RRule.EndType = 'ByDate'
    source.RRule.Until = date(2026, 10, 26)
    source.RRule.ExceptionDates.append(date(2026, 10, 26))
    event = BackupReader('.')._map_pyolk_event(source)
    assert _filter_future([event], CUTOFF) == []


def test_changed_occurrence_keeps_original_time_and_series_uid(tmp_path):
    master = mapped_event()
    original = datetime(2026, 10, 12, 10)
    windows_minutes = int((original - datetime(1601, 1, 1)).total_seconds() / 60)
    override = mapped_event(
        RecordID=2, MasterRecordID=1, RecurrenceID=windows_minutes, RRule=None,
        StartDateUTC=datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
        EndDateUTC=datetime(2026, 10, 12, 13, tzinfo=timezone.utc),
        ExchangeID='changed@example.test', IsRecurring=False,
    )
    link_overrides([master, override])
    assert override['uid'] == master['uid']
    assert override['recurrence_id'] == original.replace(tzinfo=ZONE)
    # Retain past changes alongside a live series so clients do not restore them.
    retained = _filter_future([master, override], CUTOFF)
    assert retained == [master, override]
    components = write_calendar(tmp_path, retained).walk('VEVENT')
    changed = next(component for component in components if 'RECURRENCE-ID' in component)
    assert changed.decoded('recurrence-id') == original.replace(tzinfo=ZONE)
    assert changed.decoded('dtstart') == datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    assert len({str(component['uid']) for component in components}) == 1


def test_future_moved_occurrence_keeps_its_expired_master():
    source = source_event()
    source.RRule.EndType = 'ByDate'
    source.RRule.Until = date(2026, 10, 19)
    master = BackupReader('.')._map_pyolk_event(source)
    override = {
        'uid': master['uid'], 'recurrence_id': datetime(2026, 10, 19, 10, tzinfo=ZONE),
        'start': CUTOFF + timedelta(hours=12), 'end': CUTOFF + timedelta(hours=13),
    }
    assert _filter_future([master, override], CUTOFF) == [master, override]


def test_final_occurrence_moved_to_past_does_not_keep_expired_series():
    source = source_event()
    source.RRule.EndType = 'ByDate'
    source.RRule.Until = date(2026, 10, 26)
    master = BackupReader('.')._map_pyolk_event(source)
    override = {
        'uid': master['uid'], 'recurrence_id': CUTOFF + timedelta(hours=10),
        'start': CUTOFF - timedelta(days=1), 'end': CUTOFF - timedelta(days=1, hours=-1),
    }
    assert _filter_future([master, override], CUTOFF) == []


def test_cancelled_override_is_serialized(tmp_path):
    event = mapped_event(RRule=None)
    event['recurrence_id'] = datetime(2026, 10, 5, 10, tzinfo=ZONE)
    event['is_cancelled'] = True
    component = write_calendar(tmp_path, [event]).walk('VEVENT')[0]
    assert str(component['STATUS']) == 'CANCELLED'


def test_all_day_recurrence_keeps_date_values(tmp_path):
    source = source_event(StartDateUTC=date(2026, 10, 5), EndDateUTC=date(2026, 10, 6), AllDayEvent=True)
    source.RRule.EndType = 'ByDate'
    source.RRule.Until = date(2026, 11, 2)
    event = BackupReader('.')._map_pyolk_event(source)
    assert _filter_future([event], CUTOFF) == [event]
    component = write_calendar(tmp_path, [event]).walk('VEVENT')[0]
    assert type(component.decoded('dtstart')) is date
    assert type(component['rrule']['UNTIL'][0]) is date
    assert type(component['exdate'].dts[0].dt) is date


@pytest.mark.parametrize('kind,interval,month_day,day,set_pos,expected', [
    ('Daily', 1, None, None, None, 'DAILY'),
    ('Weekly', 2, None, 'MO,WE', None, 'WEEKLY'),
    ('Monthly', 12, 5, None, None, 'MONTHLY'),
    ('MonthNth', 1, None, 'FR', -1, 'MONTHLY'),
    ('Yearly', 1, 5, None, None, 'YEARLY'),
])
def test_rule_variants(kind, interval, month_day, day, set_pos, expected):
    source = source_event()
    source.RRule.RecurrenceType = kind
    source.RRule.Interval = interval
    source.RRule.MonthDay = month_day
    source.RRule.Day = day
    source.RRule.SetPos = set_pos
    result = recurrence_fields(source)['rrule']
    assert result['freq'] == expected
    assert result['interval'] == interval
    if set_pos:
        assert result['bysetpos'] == set_pos


def test_single_events_ending_today_are_retained_and_yesterday_removed():
    yesterday = {'start': CUTOFF - timedelta(days=1), 'end': CUTOFF - timedelta(hours=1)}
    today = {'start': CUTOFF + timedelta(hours=10), 'end': CUTOFF + timedelta(hours=11)}
    assert _filter_future([yesterday, today], CUTOFF) == [today]


def test_empty_export_replaces_stale_calendar(tmp_path):
    output = tmp_path / 'calendar.ics'
    output.write_text('stale content')
    CalendarArchiver().export_ics([], str(output))
    assert Calendar.from_ical(output.read_bytes()).walk('VEVENT') == []
