import inspect
import json
import random
import tempfile
import warnings

from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from lock import FileLock

__all__ = [
    "DatabaseError",
    "WallpaperDatabase",
    "open",
    "create",
    "refresh",
    "set_startpage",
]

#
# Codecs
#
_TYPE_KEY = "_type"

class _Decoder:
    def __init__(self, data_class):
        self.data_class = data_class

    def decode(self, obj):
        if _TYPE_KEY in obj:
            type_ = obj[_TYPE_KEY]
            del obj[_TYPE_KEY]
            match type_:
                case "datetime":
                    return datetime.fromisoformat(obj["datetime"]).astimezone()
                case "PosixPath":
                    return Path(obj["path"])
                case self.data_class:
                    return vars(obj)
                case _:
                    return getattr(self.data_class, type_)(**obj)
        else:
            return obj


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if inspect.isclass(type(obj)):
            type_attr = {_TYPE_KEY: obj.__class__.__name__}
            if hasattr(obj, "__dict__"):
                return obj.__dict__ | type_attr
            elif isinstance(obj, datetime):
                return {"datetime": obj.isoformat()} | type_attr
            elif isinstance(obj, Path):
                return {"path": str(obj)} | type_attr
            else:
                raise TypeError(
                    f"Object type {obj.__class__.__name__} cannot be serialised"
                )
        else:
            return super().default(obj)


#
# Exceptions
#
class DatabaseError(Exception):
    def __init__(self, message, note=None):
        super().__init__(message)
        if note:
            self.add_note(note)

    def __str__(self):
        message = super().__str__()
        if self.__cause__:
            message += " " + str(self.__cause__)
        return message


class DatabaseDirectoryNotFoundError(DatabaseError):
    pass


class DatabaseModeError(DatabaseError):
    pass


class DatabaseLockError(DatabaseError):
    pass


class DatabaseReadError(DatabaseError):
    pass


class DatabaseExistsError(DatabaseError):
    pass


class DatabaseDecodeError(DatabaseError):
    pass


class DatabaseWriteError(DatabaseError):
    pass


class StartpageSetError(DatabaseError):
    pass


#
# Wallpaper Data
#
@dataclass
class _WallpaperData:
    @dataclass
    class Target:
        updated_at: datetime | None = None
        current: Path | None = None

    @dataclass
    class Wallpaper:
        startpage_used: bool = False
        mobile_suitable: bool = False
        mobile_used: bool = False

    base_directory: Path | None = None
    wallpapers: dict[str, Wallpaper] = field(default_factory=dict)
    updated_at: datetime | None = None
    created_at: datetime | None = None
    should_update: bool = False
    startpage: Target = field(default_factory=Target)


class WallpaperDatabase(_WallpaperData):
    # 'r' Open existing database for reading only (default)
    # 'w' Open existing database for reading and writing
    # 'c' Open database for reading and writing, creating it if it doesn’t exist
    # 'n' Always create a new, empty database, open for reading and writing
    def __init__(self, database_path, mode="r"):
        self._db_path = Path(database_path)
        self._mode = mode
        self._writeback = False

        self._open()

    def __enter__(self):
        if self._mode != "r":
            self._writeback = True
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if exc_type is None and self._writeback:
            self.save()
        self.close()

    def _open(self):
        try:
            mode = {
                "r": "r",
                "w": "r+",
                "n": "w+",
                "c": "x",
            }[self._mode]
        except KeyError as err:
            raise DatabaseModeError(
                f'Invalid mode "{self._mode}". Must be one of: "r", "w", "c", or "n".'
            ) from err

        try:
            self._file_object = self._db_path.open(mode, encoding="utf-8")
        except FileExistsError as err:
            raise DatabaseExistsError("Database already exists.") from err
        except OSError as err:
            raise DatabaseReadError("Unable to open database.") from err

        try:
            self._lock = FileLock(self._file_object, self._mode == "r")
            self._lock.acquire()
        except OSError as err:
            raise DatabaseLockError("Unable to lock database") from err

        if self._mode in ("r", "w"):
            try:
                db_dict = json.load(
                    self._file_object, object_hook=_Decoder(WallpaperDatabase).decode
                )
            except json.JSONDecodeError as err:
                raise DatabaseDecodeError("Failed to load database.") from err
            else:
                super().__init__(**db_dict)

    def save(self):
        self._file_object.seek(0)
        self._file_object.truncate()
        attrs = {k: v for k, v in vars(self).items() if not k.startswith("_")}
        try:
            json.dump(attrs, self._file_object, indent=4, cls=_Encoder)
        except OSError as err:
            raise DatabaseWriteError("Failed to write database.") from err

    def close(self):
        try:
            if self._lock.locked:
                self._lock.release()
        except OSError:
            warnings.warn("Failed to release lock on database", UserWarning)
        if not self._file_object.closed:
            self._file_object.close()

    @property
    def database_info(self):
        DatabaseInfo = namedtuple(
            "DatabaseInfo",
            [
                "database_path",
                "wallpaper_directory",
                "total_wallpapers",
                "created_at",
                "updated_at",
                "should_update",
            ],
        )
        return DatabaseInfo(
            self._db_path,
            self.base_directory,
            len(self.wallpapers),
            self.created_at,
            self.updated_at,
            self.should_update,
        )

    @property
    def startpage_info(self):
        StartpageInfo = namedtuple(
            "StartpageInfo",
            [
                "current",
                "updated_at",
            ],
        )
        return StartpageInfo(
            self.startpage.current,
            self.startpage.updated_at,
        )


# convenience function to open WallpaperDatabase
def open(database_path, mode="r"):
    return WallpaperDatabase(database_path, mode)


def create(database_path, base_directory, force=False):
    if not base_directory.is_dir():
        raise DatabaseDirectoryNotFoundError(
            f'Base directory for wallpapers does not exist "{base_directory}"'
        )
    if not database_path.parent.is_dir():
        database_path.parent.mkdir()

    if force:
        mode = "n"
    else:
        mode = "c"

    with open(database_path, mode=mode) as db:
        walls = _list_wallpapers(base_directory)
        db.base_directory = base_directory
        db.wallpapers = dict.fromkeys(walls, _WallpaperData.Wallpaper())
        db.created_at = datetime.now()
        db_info = db.database_info

    return db_info


def refresh(database_path):
    with open(database_path, mode="w") as db:
        walls_disk = set(_list_wallpapers(db.base_directory))
        walls_db = set(db.wallpapers.keys())
        walls_deleted = walls_db.difference(walls_disk)
        walls_new = walls_disk.difference(walls_db)

        db.wallpapers.update(dict.fromkeys(walls_new, _WallpaperData.Wallpaper()))
        for wall in walls_deleted:
            del db.wallpapers[wall]

        db.updated_at = datetime.now()

    Changes = namedtuple("Changes", ["new", "deleted"])
    return Changes(len(walls_new), len(walls_deleted))


def _list_wallpapers(directory):
    # + 1 to account for trailing slash in directory
    dir_len = len(str(directory)) + 1
    walls = []
    for file in directory.rglob("*"):
        # Exclude hidden files and directories, and non-image extensions
        if any(part for part in file.parts if part[0] == ".") or file.suffix not in (
            ".png",
            ".jpeg",
            ".jpg",
            ".gif",
        ):
            continue
        walls.append(str(file)[dir_len:])
    return walls


def set_startpage(database_path, exclusions, startpage_background):
    def _set_startpage():
        for _ in range(len(walls_unused)):
            wall_new = random.choice(walls_unused)
            wall_path = db.base_directory / wall_new
            if wall_path.is_file():
                with tempfile.TemporaryDirectory() as dir:
                    symlink = Path(dir, "wdb_symlink")
                    symlink.symlink_to(wall_path.absolute())
                    symlink.replace(startpage_background)
                db.wallpapers[wall_new].startpage_used = True
                db.startpage.current = wall_path
                db.startpage.updated_at = datetime.now()
                return True
            else:
                walls_unused.remove(wall_new)
                warnings.warn(
                    "Database contains non-existent file and should be refreshed",
                    UserWarning,
                )
                db.should_update = True
        return False

    with open(database_path, mode="w") as db:
        walls_filtered = filter(
            lambda p: not any(ex in p for ex in exclusions), db.wallpapers
        )

        walls_included = {k: db.wallpapers[k] for k in walls_filtered}
        if len(walls_included) == 0:
            raise StartpageSetError(
                "No available wallpapers after applying exclusions!",
                "Is your list too broad?",
            )

        walls_unused = [
            k for k, v in walls_included.items() if v.startpage_used is False
        ]

        for _ in range(2):
            if _set_startpage():
                break
            elif len(walls_unused) == 0:
                # reached the end of the list so reset startpage_used
                walls_unused = list(walls_included.keys())
                for k, v in db.wallpapers.items():
                    v.startpage_used = False
        else:
            raise StartpageSetError(
                "Unable to set startpage wallpaper. No valid files within database"
            )
