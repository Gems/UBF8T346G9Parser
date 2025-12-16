import pathlib


class Helper:
    """Helper class with sorta random helper methods
    """

    @staticmethod
    def test_location(location: str, location_type: str) -> str:
        location_path = pathlib.Path(location)
        if location_type == 'folder' and not location_path.is_dir():
            raise NotADirectoryError(f'{location} is not a directory')
        if location_type == 'file' and not location_path.is_file():
            raise FileNotFoundError(f'{location} is not a file')
        return location

    @staticmethod
    def _get_backup_location(quiet: bool = False):
        default = './UBF8T346G9.Office/'
        if quiet:
            return default

        userinput = input(
            f'Please provide backup folder location [Default: {default}]: ')
        return userinput or default

    @staticmethod
    def _get_profile_data(quiet: bool = False):
        static_path = 'Outlook/Outlook 15 Profiles/{}/Data/'
        default = 'Main Profile'
        if quiet:
            return static_path.format(default)

        userinput = input(
            f'Please provide user profile [Default: {default}]: ')
        return static_path.format(userinput or default)

    @classmethod
    def get_location(cls, quiet: bool = False) -> str:
        return cls._get_backup_location(quiet=quiet) + cls._get_profile_data(quiet=quiet)
