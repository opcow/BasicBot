import click
import daemonocle
import configparser
from pwd import getpwnam
from basicbot import BasicBot

try:
    import pydevd

    pydevd.settrace('192.168.3.7', port=32333, stdoutToServer=True, stderrToServer=True)
    DEBUGGING = True
except ImportError:
    DEBUGGING = False


class App():
    def __init__(self, channel, nick, server, port, ipv6, username, password, trigger, secret, logfile, loglevel):
        self.bot = BasicBot(channel, nick, server, port, username, password, ipv6, cmd_trigger=trigger, secret=secret,
                            logfile=logfile, loglevel=loglevel)
        self.bot.config_buffer()

    def run(self):
        self.bot.start()

    def shutdown(self, message, code):
        self.bot.shutdown()


def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo('Basicbot Version 1.0')
    ctx.exit()


def print_format(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo("[ServerName]")
    click.echo("Channel = #botchannel")
    click.echo("Nick = mynick,myaltnick,myaltnick_")
    click.echo("Address = irc.example.net")
    click.echo("Port = 6660")
    click.echo("IPv6 = False")
    click.echo("Username = myusername")
    click.echo("Password = secret")
    click.echo()
    click.echo(
        '"[ServerName]" is a unique name for the server. Can be anything you want to identify this server (required).')
    click.echo('"Channel" is a single channel which the bot should join (required).')
    click.echo('"Nick" is comma separated list of one or more nicknames the bot should try to use (required).')
    click.echo('"Address" is the address of the server (optional if the server name is the address).')
    click.echo('"Port" is the server\'s port (optional, defaults to 6667).')
    click.echo('"IPv6" should be used if the server address is and IPv6 address (optional, defaults to false).')
    click.echo(
        '"Username" is the username for the server, if required (optional, defaults to the same as the nickname).')
    click.echo('"Password" is the password for the server, if required (optional, defaults to no password).')
    click.echo()
    click.echo(
        'The server name is case sensitive. Option names are not. Any option can be left out, but required items must be supplanted by command line options.')
    click.echo()
    ctx.exit()


@click.group()
@click.option('--version', is_flag=True, callback=print_version, expose_value=False, is_eager=True,
              help='Print the Basicbot version.')
@click.option('--format', is_flag=True, callback=print_format, expose_value=False, is_eager=True,
              help='Print an example config file.')
def cli():
    pass


@cli.command()
@click.option('--workdir', '-k', default='/', type=click.Path(exists=True), help='Working directory for the bot.')
@click.option('--pidfile', '-i', type=click.Path(exists=False),
              help='PID file for the bot. (Required if the start and stop commands are to be used.)')
@click.option('--user', type=str, help='User to run the bot under.')
@click.option('--group', type=str, help='Group to run the bot under.')
@click.option('--detach/--no-detach', default=True, help='Detach the bot ot run in the foreground.')
@click.option('--file', '-f', type=click.Path(exists=True), help='A file to read the settings from.')
@click.option('--channel', '-c', help='The channel to join.')
@click.option('--nick', '-n', help="The bot's nickname.")
@click.option('--server', '-s', default='localhost',
              help=' Address of the server to join or the server from the config file.')
@click.option('--port', '-p', default=6667, help="The server's port.")
@click.option('--ipv6', '-6', is_flag=True, help="Use if the server's address is IPv6.")
@click.option('--username', '-u', help="The bot's IRC username.")
@click.option('--password', '-w', help="The bot's IRC server password.")
@click.option('--trigger', '-t', default='.', help="The string the bot should respond to.")
@click.option('--secret', help="A password for secured bot commands.")
@click.option('--logfile', '-l', default=None, help="Default is sdout or supply a file (/dev/log for the system log).")
@click.option('--loglevel', '-e', default=20,
              help="Minimum event level of log output. Default is 20. Use 10 for debug output.")
def start(workdir, pidfile, user, group, detach, file, channel, nick, server, port, ipv6, username, password, trigger,
          secret, logfile, loglevel):
    if file is not None:
        cf = configparser.ConfigParser()
        try:
            cf.read(file)
            if server is None: server = 'default'
            if server not in cf:
                click.secho('Server %s not found in %s.' % (server, file), bold=True)
                exit(1)

            section = cf[server]
            channel = section.get('Channel', channel)
            nick = nick or section.get('Nick', nick)
            server = section.get('Address', server)
            port = section.getint("Port", port)
            ipv6 = section.getboolean('IPv6', False)
            username = username or section.get('Username', username)
            password = password or section.get('Password', password)
        except configparser.ParsingError as err:
            click.echo(err)
            exit(1)

    if user is not None:
        user = getpwnam(user).pw_uid
    if group is not None:
        group = getpwnam(group).pw_gid
    daemon = daemonocle.Daemon(
        workdir=workdir,
        pidfile=pidfile,
        detach=detach,
        close_open_files=True,
        uid=user,
        gid=group,
    )
    if not (channel and server and nick):
        if channel is None: click.secho('A channel name is required.', bold=True)
        if server is None: click.secho('A server address is required.', bold=True)
        if nick is None: click.secho('A nick is required.', bold=True)
        exit(1)
    click.echo('Connecting to server %s (%s) as %s...' % (server, port, nick))
    app = App(channel, nick, server, port, ipv6, username, password, trigger, secret, logfile, loglevel)
    daemon.worker = app.run
    daemon.shutdown_callback = app.shutdown
    try:
        daemon.do_action('start')
    except (daemonocle.exceptions.DaemonError, FileNotFoundError, PermissionError) as err:
        print(err)


@cli.command()
@click.option('--pidfile', '-i', type=click.Path(exists=False), help='PID file for the bot.', required=True)
def stop(pidfile):
    daemon = daemonocle.Daemon(
        pidfile=pidfile,
    )

    try:
        daemon.do_action('stop')
    except (daemonocle.exceptions.DaemonError, FileNotFoundError, PermissionError) as err:
        print(err)


@cli.command()
@click.option('--pidfile', '-i', type=click.Path(exists=False), help='PID file for the bot.', required=True)
def status(pidfile):
    daemon = daemonocle.Daemon(
        pidfile=pidfile,
    )

    try:
        daemon.do_action('status')
    except (daemonocle.exceptions.DaemonError, FileNotFoundError) as err:
        print(err)


if __name__ == '__main__':
    cli()
