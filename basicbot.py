#!/usr/bin/env python3

import irc
from irc import bot
import logging
import logging.handlers
import sys

def create_logger(file, level, botname):
        FORMAT = '%(levelname)s: {} on %(host)s:%(port)s: %(message)s'.format(botname)
        if file == '/dev/log':
            bot_log = logging.handlers.SysLogHandler(address=file)
        elif file is not None:
            bot_log = logging.FileHandler(file)
        else:
            bot_log = logging.StreamHandler(sys.stdout)
        bot_log.setFormatter(logging.Formatter(FORMAT))
        logger = logging.getLogger('{}-log'.format(botname))
        logger.setLevel(level)
        logger.addHandler(bot_log)
        return logger


class BasicBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port=6667, username=None, password=None, ipv6=False, cmd_trigger='!',
                 secret=None, logfile=None, loglevel=10):
        self.nicks = nickname.split(',')
        self.num_nicks = len(self.nicks)
        self.nick_index = 0
        self.leaving = False
        if username is None: username = self.nicks[0]

        self.chan_list = channel.split(',')
        self.max_nick_len = 9
        self.trigger = cmd_trigger
        self.secret = secret
        factory = irc.connection.Factory(ipv6=ipv6)

        # setup logging
        self.logger = create_logger(logfile, loglevel, 'BasicBot')
        self.logdat = {'host': server, 'port': port, 'nick': nickname}

        self.logger.debug('%s',
                          'configured with (server: {} port: {} nickname: {} username: {} ipv6: {})'.format(
                              server, port, self.nicks[0], username, ipv6), extra=self.logdat)
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, password)],
                                            username, self.nicks[0], connect_factory=factory)

    def config_buffer(self):
        self.connection.buffer_class = irc.buffer.LenientDecodingLineBuffer

    def start(self):
        self.logger.info('%s', "started", extra=self.logdat)
        irc.bot.SingleServerIRCBot.start(self)

    def shutdown(self):
        self.leaving = True
        self.logger.info('%s', "shutting down", extra=self.logdat)
        if self.connection.is_connected():
            self.part_bot_channels()
            # self.connection.quit()
        #            self.connection.disconnect()
        self.die()

    def on_featurelist(self, c, e):
        for f in e.arguments:
            # get the max nick length
            if f.startswith('NICKLEN='):
                self.max_nick_len = int(f[len('NICKLEN='):])
                self.logger.debug('%s', 'Maximum nick length set to: {}'.format(self.max_nick_len),
                                  extra=self.logdat)

    # change nick if needed, by cycling through the list of alts
    def change_nick(self):
        if self.nick_index >= self.num_nicks:
            self.logger.critical('%s', "couldn't get a nick: {}".format(self.nicks), extra=self.logdat)
            self.shutdown()
        new_nick = self.nicks[self.nick_index][-self.max_nick_len:]
        self.logger.debug('%s', 'attempting to change nick to {}'.format(new_nick), extra=self.logdat)
        self.connection.nick(new_nick)

    def on_nicknameinuse(self, c, e):
        self.logger.debug('%s', 'nickname in use ({})'.format(self.connection.get_nickname()), extra=self.logdat)
        self.nick_index += 1
        self.change_nick()

    def on_erroneusnickname(self, c, e):
        self.logger.warning('%s', '{} {}'.format(e.arguments[0], e.arguments[1]), extra=self.logdat)
        self.shutdown()

    # join any channels in the chan list if we're not already there
    def join_bot_channels(self):
        # don't do this if we are about to quit
        if self.leaving == False:
            for chan in self.chan_list:
                if not chan in self.channels.keys():
                    self.logger.debug('%s', 'joining channel: {}'.format(chan), extra=self.logdat)
                    self.connection.join(chan)

    # join any channels in the chan list if we're not already there
    def part_bot_channels(self):
        for chan in self.channels.keys():
            self.logger.debug('%s', 'parting channel: {}'.format(chan), extra=self.logdat)
            self.connection.part(chan)

    def on_unavailresource(self, c, e):
        self.logger.warning('%s', '{}, {}'.format(e.arguments[0], e.arguments[1]), extra=self.logdat)
        if e.arguments[0] == c.get_nickname():
            self.nick_index += 1
            self.change_nick()
            # if e.arguments[0] in self.chan_list:
            # c.execute_delayed(120, self.join_bot_channels)
            #     pass

    def on_welcome(self, c, e):
        # self.connection.buffer.errors = 'replace'
        self.change_nick()
        # wait 5 seconds then join channels
        c.execute_delayed(5, self.join_bot_channels)
        # try every 120s to join any configured channels we aren't in
        c.execute_every(120, self.join_bot_channels)

    def on_privmsg(self, c, e):
        if e.arguments[0].startswith(self.secret):
            if e.arguments[0][len(self.secret)+1:] == 'die':
                self.logger.debug('%s', 'got shutdown command from {}'.format(e.source), extra=self.logdat)
                self.shutdown()

    def on_pubmsg(self, c, e):
        if e.arguments[0].startswith(self.trigger):
            cmd = e.arguments[0][len(self.trigger):].lower()
            self.logger.debug('%s', 'got command "{}" from {} in {}'.format(cmd, e.source, e.target), extra=self.logdat)
            # TODO: add command processing

    def _on_kick(self, c, e):
        # remove channel from the list if we're kicked, so we won't rejoin
        try:
            if e.arguments[0] == c.get_nickname():
                self.logger.info('%s', 'kicked from {} by {}'.format(e.target, e.source), extra=self.logdat)
                self.chan_list.remove(e.target)
        except ValueError as err:
            self.logger.error('%s', 'error ({}) in on_kick trying to remove {} from channel list'.format(err, e.target),
                              extra=self.logdat)

