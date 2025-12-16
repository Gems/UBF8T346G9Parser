#!/usr/bin/env python
import argparse

from backupreader import reader
from olk15parser import parser
from helpers.helpers import Helper


def _parse_args() -> argparse.Namespace:
    arg_parser = argparse.ArgumentParser(
        description="Parse Outlook 2016 backups and slice message HTML.")
    arg_parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Use default paths without prompting for input.")
    return arg_parser.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    profile_data_location = Helper.get_location(quiet=args.quiet)

    backupreader_app = reader.backupreader(profile_data_location)
    olk15parser_app = parser.olk15parser()

    for i, mail in enumerate(backupreader_app.get_mails_from_database()):
        mail_path = profile_data_location + mail.get('content_path')
        print(i, mail)
        message = olk15parser_app.get_mail_content(mail_path, mail.get('subject'))
