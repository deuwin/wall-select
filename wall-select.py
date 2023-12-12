#!/usr/bin/env python3

import argparse
import sys
import locale
import warnings

from collections import namedtuple

import wsconfig
import wallpaperdatabase as wdb

from argparsesubcommand import HelpFormatterSubcommand


#
# Printing and Formatting
#
def format_timestamp(timestamp):
    # use system's locale for date display
    locale.setlocale(locale.LC_ALL, "")
    if timestamp:
        return timestamp.strftime("%c")
    else:
        return "N/A"


def print_aligned(key_values):
    # plus one for additional colon
    longest_key = len(max(key_values, key=len)) + 1
    line = [f"{f'{k}:':<{longest_key}} {v}" for k, v in key_values.items()]
    print(*line, sep="\n")


def print_error(error):
    if isinstance(error, Exception):
        prefix = f"{type(error).__name__}: "
    else:
        prefix = "Error: "
    print(prefix + str(error), file=sys.stderr)
    if hasattr(error, "__notes__"):
        for n in error.__notes__:
            print(f"Note: {n}", file=sys.stderr)


def warning_short(message, category, filename, lineno, file=None, line=None):
    return f"Warning: {message}\n"


warnings.formatwarning = warning_short


def print_warning(message):
    print(f"Warning: {message}", file=sys.stderr)


#
# Database Functions
#
def print_database_info(config):
    with wdb.open(config.database_path) as db:
        db_info = db.database_info
        print_aligned(
            {
                "Database Location": db_info.database_path,
                "Wallpaper Directory": db_info.wallpaper_directory,
                "Total Wallpapers": db_info.total_wallpapers,
                "Created": format_timestamp(db_info.created_at),
                "Last Update": format_timestamp(db_info.updated_at),
                "Requires Update": db_info.should_update,
            }
        )


def create_database(config, force=False):
    for _ in range(2):
        try:
            db_info = wdb.create(
                config.database_path, config.wallpaper_directory, force
            )
        except wdb.DatabaseExistsError:
            response = input("Database file already exists. Overwrite it? [y/N]: ")
            if response.lower() in ("y", "yes"):
                force = True
            else:
                print("Cancelling database creation")
                break
        else:
            print("Database created!")
            print_aligned(
                {
                    "Database Location": db_info.database_path,
                    "Wallpaper Directory": db_info.wallpaper_directory,
                    "Total Wallpapers": db_info.total_wallpapers,
                    "Created": format_timestamp(db_info.created_at),
                }
            )
            break


def refresh_database(config):
    changes = wdb.refresh(config.database_path)
    print("Database updated!")
    print_aligned(
        {
            "New": changes.new,
            "Deleted": changes.deleted,
        }
    )


#
# Startpage Functions
#
def set_startpage_wallpaper(config):
    new_wall = wdb.set_startpage(
        config.database_path, config.exclude["startpage"], config.startpage_background
    )
    print(f"Startpage set!\n{new_wall}")


def print_startpage_info(config):
    with wdb.open(config.database_path) as db:
        sp_info = db.startpage_info
        print_aligned(
            {
                "Current Wallpaper": sp_info.current,
                "Last Change": format_timestamp(sp_info.updated_at),
            }
        )


#
# Arguments
#
Subcommand = namedtuple("Subcommand", ["operations", "help", "aliases"])
Operation = namedtuple("Operation", ["function", "help", "aliases"], defaults=[[]])
SUBCOMMANDS = {
    "database": Subcommand(
        aliases=["db"],
        help="manipulate wallpaper database",
        operations={
            "create": Operation(
                function=create_database,
                help="create wallpaper database",
            ),
            "refresh": Operation(
                function=refresh_database,
                help=(
                    "update database with any changes made to the "
                    "files in 'base_directory'"
                ),
            ),
            "info": Operation(
                function=print_database_info,
                help="display information about database",
            ),
        },
    ),
    "startpage": Subcommand(
        aliases=["sp"],
        help="change or inspect startpage background",
        operations={
            "info": Operation(
                function=print_startpage_info,
                help="display information about current startpage background",
            ),
            "set-wall": Operation(
                function=set_startpage_wallpaper,
                help="update current startpage background",
                aliases=["set"],
            ),
        },
    ),
}


def parse_arguments(argv):
    parser = argparse.ArgumentParser(
        formatter_class=HelpFormatterSubcommand,
        exit_on_error=False,
        epilog="See '%(prog)s <command> {-h | --help}' for available "
        "commands in the given <command>.",
    )
    subparsers = parser.add_subparsers(
        dest="cmd_arg",
        metavar="<command>",
    )

    cmd_parser = {}
    for cmd_name, cmd_attrs in SUBCOMMANDS.items():
        cmd_parser[cmd_name] = subparsers.add_parser(
            cmd_name,
            aliases=cmd_attrs.aliases,
            help=cmd_attrs.help,
            formatter_class=HelpFormatterSubcommand,
            exit_on_error=False,
        )
        cmd_parser[cmd_name].set_defaults(command=cmd_name)
        cmd_operations = cmd_parser[cmd_name].add_subparsers(
            dest="op_arg",
            metavar="<operation>",
        )
        for op_name, op_attrs in SUBCOMMANDS[cmd_name].operations.items():
            op_parser = cmd_operations.add_parser(
                op_name, help=op_attrs.help, aliases=op_attrs.aliases
            )
            op_parser.set_defaults(operation=op_name, function=op_attrs.function)

    # check for invalid commands
    try:
        args = parser.parse_args(argv[1:])
    except argparse.ArgumentError as err:
        print_error(err)
        parser.print_help(sys.stderr)
        exit(FAILURE)

    # check for missing operands
    if not args.command:
        print_error("Missing <command> operand")
        parser.print_help(sys.stderr)
        exit(FAILURE)
    if not args.operation:
        print_error("Missing <operation> operand")
        cmd_parser[args.command].print_help(sys.stderr)
        exit(FAILURE)

    return args


#
# Main
#
SUCCESS = 0
FAILURE = 1

def main(argv):
    try:
        config = wsconfig.read()
    except wsconfig.ConfigError as err:
        print_error(err)
        return FAILURE

    args = parse_arguments(argv)
    try:
        args.function(config)
    except wdb.DatabaseError as err:
        exit_code = FAILURE
        print_error(err)
    else:
        exit_code = SUCCESS
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
