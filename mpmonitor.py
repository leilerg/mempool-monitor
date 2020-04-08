"""
Entry point to the app
"""

import os
import sys
import time
import signal
import lockfile
import logging
import logging.config

import daemon
from pid import PidFile

from mpmonitor.monitor import MempoolMonitor


PIDDIR = os.path.dirname(os.path.abspath(__file__))
PIDNAME = "mpmonitor.pid"
PIDFILE = os.path.join(PIDDIR, PIDNAME)

LOGCONF = "logging.conf"


logging.config.fileConfig(fname=LOGCONF, disable_existing_loggers=False)
log = logging.getLogger(__file__)




def get_logging_handles(logger):
    handles = []
    for handler in logger.handlers:
        handles.append(handler.stream.fileno())
    if logger.parent:
        handles += get_logging_handles(logger.parent)
    return handles



def start():
    # print("Starting Mempool Monitor")
    log.info("Starting Mempool Monitor")


    _pid_file = PidFile(pidname=PIDNAME, piddir=PIDDIR)

    # Files to preserve (i.e. not close) on forking the process
    # (A daemon forks the process and closes all the associated open files)
    _files_preserve = get_logging_handles(logging.root)
    
    with daemon.DaemonContext(stdout=sys.stdout,
                              stderr=sys.stderr,
                              stdin=sys.stdin,
                              files_preserve=_files_preserve,
                              pidfile=_pid_file):

        # Start the monitor:
        mpmonitor = MempoolMonitor()
        mpmonitor.run()
    

def stop():
    log.info("Stopping mempool monitor")

    try:
        # with open(pid_file, "r") as f:
        with open(PIDFILE, "r") as f:
            content = f.read()
        f.close()
        pid = int(content)
        log.info("Process PID obtained \n({})".format(PIDFILE))

    except FileNotFoundError as fnf_err:
        print("WARNING - PID file not found, cannot stop daemon.\n({})".format(PIDFILE))
        log.warning("WARNING - PID file not found, cannot stop daemon.\n({})".format(PIDFILE))
        sys.exit()


    os.kill(pid, signal.SIGTERM)

    print("Mempool monitor stopped.")
    log.info("Mempool monitor stopped.")
    
    sys.exit()


if __name__ == "__main__":

    try:
        run_arg = sys.argv[1]

    except IndexError as index_err:
        print("\nMPMonitor called with no command - No actions taken. Pass \"--help\" for "
              "available options.\n") 
        sys.exit()
        

    if run_arg=="--help":
        print("\nMempool monitor: Aims to collect data about the block when a transaction is " 
              "first seen.")
        print("The data is saved to database.\n\n")
        print("Commands:\n")
        print("start")
        print("\tStart the daemon.\n")
        print("stop")
        print("\tStop the daemon.\n\n")

    curr_dir = os.getcwd()
    pid_file = os.path.join(curr_dir, "mpmonitor.pid")

    if run_arg=="start":
        start()

    if run_arg=="stop":
        stop()


    print("\nUnknown command, re-run with \"--help\" for supported commands.\n")

