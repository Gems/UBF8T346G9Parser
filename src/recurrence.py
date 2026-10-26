"""Preserve Outlook series, local recurrence times, and changed occurrences."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from icalendar import vRecur


def occurrence_on(day, start):
    """Give an Outlook recurrence date the series' original local start time."""
    if isinstance(day, datetime):
        day = day.date()
    if isinstance(start, datetime):
        return datetime.combine(day, start.timetz())
    return day


def recurrence_fields(event):
    """Translate a parsed pyolk rule into RFC 5545 fields."""
    rule = getattr(event, 'RRule', None)
    if not rule:
        return {}

    start = event.StartDateUTC
    end = event.EndDateUTC
    if isinstance(start, datetime):
        zone = ZoneInfo(event.Timezone.TZID)
        start = start.astimezone(zone)
        end = end.astimezone(zone)

    frequencies = {
        'Daily': 'DAILY', 'Weekly': 'WEEKLY', 'Monthly': 'MONTHLY',
        'MonthNth': 'MONTHLY', 'Yearly': 'YEARLY', 'YearNth': 'YEARLY',
    }
    # Outlook also represents yearly patterns as Monthly with Interval=12.
    frequency = frequencies[rule.RecurrenceType]
    recurrence = {'freq': frequency, 'interval': int(rule.Interval)}
    if getattr(rule, 'Day', None):
        recurrence['byday'] = rule.Day.split(',')
    if getattr(rule, 'MonthDay', None):
        recurrence['bymonthday'] = rule.MonthDay
    if getattr(rule, 'SetPos', None):
        recurrence['bysetpos'] = rule.SetPos
    if frequency == 'YEARLY':
        recurrence['bymonth'] = start.month

    if rule.EndType == 'ByDate':
        until = rule.Until
        if isinstance(start, datetime):
            until = datetime.combine(until, time.max, start.tzinfo)
            until = until.astimezone(timezone.utc).replace(microsecond=0)
        recurrence['until'] = until
    elif rule.EndType == 'AfterCount':
        recurrence['count'] = int(rule.Occurrences)
    elif rule.EndType != 'None':
        raise ValueError(f'Unsupported Outlook recurrence end type: {rule.EndType}')

    return {
        'start': start,
        'end': end,
        'rrule': recurrence,
        'exdates': [occurrence_on(day, start) for day in rule.ExceptionDates],
    }


def link_overrides(events):
    """Use one UID for a series and identify the original time of each override."""
    masters = {event['id']: event for event in events if event.get('rrule')}
    for event in events:
        master = masters.get(event.get('master_id'))
        if master is None:
            continue
        event['uid'] = master['uid']
        # RecurrenceID is a Windows-minute value in the organizer's wall time.
        original = datetime(1601, 1, 1) + timedelta(minutes=event['recurrence_id'])
        event['recurrence_id'] = occurrence_on(original.date(), master['start'])


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min)


def _ends_on_or_after(event, cutoff):
    end = event.get('end') or event.get('start')
    if end is None:
        return True
    if isinstance(end, (datetime, date)):
        end = _as_datetime(end)
    else:
        try:
            end = datetime.fromtimestamp(float(end))
        except (TypeError, ValueError, OverflowError):
            return True
    boundary = cutoff.astimezone(end.tzinfo) if end.tzinfo else cutoff.replace(tzinfo=None)
    return end >= boundary


def filter_future(events, cutoff):
    """Keep series with future instances, together with their changed instances."""
    overrides = {}
    for event in events:
        if isinstance(event.get('recurrence_id'), date):
            overrides.setdefault(event['uid'], []).append(event)

    retained_series = set()
    for event in events:
        if not event.get('rrule'):
            continue
        changed = overrides.get(event['uid'], [])
        start = _as_datetime(event['start'])
        end = _as_datetime(event['end'])
        boundary = cutoff.astimezone(start.tzinfo) if start.tzinfo else cutoff.replace(tzinfo=None)
        rule = vRecur(event['rrule']).to_ical().decode('ascii')
        instances = rrulestr(rule, dtstart=start, forceset=True)
        for excluded in event.get('exdates', []):
            instances.exdate(_as_datetime(excluded))
        for override in changed:
            instances.exdate(_as_datetime(override['recurrence_id']))
        if (instances.after(boundary - (end - start), inc=True) is not None
                or any(_ends_on_or_after(override, cutoff) for override in changed)):
            retained_series.add(event['uid'])

    retained = []
    for event in events:
        belongs_to_series = event.get('rrule') or isinstance(event.get('recurrence_id'), date)
        if belongs_to_series:
            keep = event['uid'] in retained_series
        else:
            keep = _ends_on_or_after(event, cutoff)
        if keep:
            retained.append(event)
    return retained
