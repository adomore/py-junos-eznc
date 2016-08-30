import paramiko
from select import select
import re

_JUNOS_PROMPT = '> '
_SHELL_PROMPT = '(%|#)\s'
_SELECT_WAIT = 0.1
_RECVSZ = 1024


class StartShell(object):

    """
    Junos shell execution utility.  This utility is written to
    support the "context manager" design pattern.  For example::

        def _ssh_exec(self, command):
            with StartShell(self._dev) as sh:
                got = sh.run(command)
            return got

    """

    def __init__(self, nc):
        """
        Utility Constructor

        :param Device nc: The Device object
        """
        self._nc = nc

    def wait_for(self, this=_SHELL_PROMPT):
        """
        Wait for the result of the command, expecting **this** prompt.

        :param str this: expected string/pattern.

        :returns: resulting string of data in a list
        :rtype: list

        .. warning:: need to add a timeout safeguard
        """
        chan = self._chan
        got = []
        while True:
            rd, wr, err = select([chan], [], [], _SELECT_WAIT)
            if rd:
                data = chan.recv(_RECVSZ)
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                got.append(data)
                if re.search(r'{0}\s?$'.format(this), data):
                    break
        return got

    def send(self, data):
        """
        Send the command **data** followed by a newline character.

        :param str data: the data to write out onto the shell.
        :returns: result of SSH channel send
        """
        self._chan.send(data)
        self._chan.send('\n')

    def open(self):
        """
        Open an ssh-client connection and issue the 'start shell' command to
        drop into the Junos shell (csh).  This process opens a
        :class:`paramiko.SSHClient` instance.
        """
        junos = self._nc

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=junos.hostname,
                       port=(22, junos._port)[junos.hostname == 'localhost'],
                       username=junos._auth_user,
                       password=junos._auth_password,
                       )

        chan = client.invoke_shell()
        self._client = client
        self._chan = chan

        got = self.wait_for(r'(%|>|#)')
        if got[-1].endswith(_JUNOS_PROMPT):
            self.send('start shell')
            self.wait_for(_SHELL_PROMPT)

    def close(self):
        """ Close the SSH client channel """
        self._chan.close()
        self._client.close()

    def run(self, command, this=_SHELL_PROMPT):
        """
        Run a shell command and wait for the response.  The return is a
        tuple. The first item is True/False if exit-code is 0.  The second
        item is the output of the command.

        :param str command: the shell command to execute
        :param str this: the exected shell-prompt to wait for

        :returns: (last_ok, result of the executed shell command (str) )

        .. note:: as a *side-effect* this method will set the ``self.last_ok``
                  property.  This property is set to ``True`` if ``$?`` is
                  "0"; indicating the last shell command was successful.
        """
        # run the command and capture the output
        self.send(command)
        got = ''.join(self.wait_for(this))

        # use $? to get the exit code of the command
        self.send('echo $?')
        rc = ''.join(self.wait_for(this))
        self.last_ok = True if rc.find('0') > 0 else False

        return (self.last_ok, got)

    # -------------------------------------------------------------------------
    # CONTEXT MANAGER
    # -------------------------------------------------------------------------

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_ty, exc_val, exc_tb):
        self.close()
