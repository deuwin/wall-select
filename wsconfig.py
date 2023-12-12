import tomllib

from collections import namedtuple
from dataclasses import dataclass
from pathlib import Path


#
# Exceptions
#
class ConfigError(Exception):
    def __init__(self, message, note):
        super().__init__(message)
        if note:
            self.add_note(note)

    def __str__(self):
        message = super().__str__()
        if self.__cause__:
            message += " " + str(self.__cause__)
        return message


#
# Data
#
@dataclass(frozen=True)
class _DefaultPath:
    config = Path.home() / ".config/wall-select.toml"
    database = Path.home() / ".local/share/wall-select.json"


Config = namedtuple(
    "Config",
    [
        "database_path",
        "wallpaper_directory",
        "startpage_background",
        "exclude",
    ],
)

#
# Functions
#
GENERAL = "general"
MOBILE = "mobile"
STARTPAGE = "startpage"

def read():
    try:
        with open(_DefaultPath.config, mode="rb") as file:
            config = tomllib.load(file)
    except OSError as err:
        raise ConfigError(
            "Unable to open config file.",
            f'Please create a config file at "{_DefaultPath.config}" using the '
            'example from "wall-select.toml.example"',
        ) from err

    excludes = {}
    for section in (GENERAL, STARTPAGE, MOBILE):
        try:
            excludes[section] = config[section]["exclude"]
        except KeyError:
            excludes[section] = []
    excludes[STARTPAGE] += excludes[GENERAL]
    excludes[MOBILE] += excludes[GENERAL]

    return Config(
        _DefaultPath.database,
        Path(config[GENERAL]["wallpaper_directory"]),
        Path(config[STARTPAGE]["background"]),
        excludes,
    )
