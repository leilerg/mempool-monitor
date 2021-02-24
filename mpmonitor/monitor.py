"""
MempoolMonitor class - Main class for the app.
"""
import os
import sys
import time
import configparser
import logging

from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

from mpmonitor.sql_db_interface import *


log = logging.getLogger(__name__)


def load_config():
    """
    Loads the config file.

    Parameters
    ----------
    None

    Returns
    -------
    config : configparser.ConfigParser()
    """
    config = None
    config_dir = os.path.dirname(os.path.realpath(__file__))
    # config_file = os.path.join(config_dir, os.pardir, "config.yaml")
    config_file = os.path.join(config_dir, os.pardir, "config.ini")

    if os.path.exists(config_file):
        # config = load_yaml_file(config_file)
        config = configparser.ConfigParser()
        config.read(config_file)

    log.info("Config loaded.")

    return config


class MempoolMonitor(object):
    """
    MempoolMonitor class - Starts the monitoring loop, requests mempool data from the bitcoin node,
    and dumps the changes to SQL database.

    Parameters
    ----------
    None (A configuration file is loaded during instantiation.)

    Returns
    -------
    None

    Examples
    --------
    >> monitor = MempoolMonitor()
    >> monitor.run()
    """

    def __init__(self):
        """
        Initialize self.
        """
        try:
            app_config = load_config()
        except Exception as err:
            log.exception(f"Unhandled exception whilst loading config.\nException: {err}")
            sys.exit()

        try:
            self.__rpc_user = app_config['RPC']['user']
            self.__rpc_pass = app_config['RPC']['pass']
            self.__rpc_host = app_config['RPC']['host']
            self.__rpc_port = app_config['RPC']['port']
            self.__rpc_http_timeout = app_config['RPC']['http_timeout']

            sql_db   = app_config["MYSQL"]["database"]
            sql_user = app_config["MYSQL"]["user"]
            sql_pass = app_config["MYSQL"]["pass"]
            sql_host = app_config["MYSQL"]["host"]

            self.__global_frequency = app_config['GLOBAL']['frequency']
        except KeyError as k_err:
            log.exception(f"Missing one or more mandatory config keys. Aborting.\n{k_err}")
            print(f"ERROR - Missing one or more mandatory config keys. Aborting.\n{k_err}")
            sys.exit()

        self.__bootstrap = True # Run bootstrapping code at first
        self.__btc_rpc_connect = None
        self.__nr_ticks = 0

        self.db = SqlDbInterface(sql_db, sql_user, sql_pass, sql_host)


    def run(self):
        """
        Main function of the monitor - Starts the mempool monitor (request data from node, analyzes
        for new transactions, and dumps data to database.)

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        while True:
            # Insantiate rpc interface
            self.__btc_rpc_connect = AuthServiceProxy(f"http://{self.__rpc_user}" +
                                                      f":{self.__rpc_pass}" +
                                                      f"@{self.__rpc_host}" +
                                                      f":{self.__rpc_port}",
                                                      timeout = int(self.__rpc_http_timeout))

            try:
                blockchain_info = self.__btc_rpc_connect.getblockchaininfo()

            except JSONRPCException as json_err:
                log.exception("JSON-RPC `getblockchaininfo` error : ", exc_info=True)
                log.exception("Resuming operation, skipping current query...")
                time.sleep(int(self.__global_frequency))
                continue

            except Exception as sto_err:
                log.exception("Unexpected exception in JSON-RPC `getblockchaininfo`:", exc_info=True)
                log.exception("Resuming operation, skipping current query...")
                time.sleep(int(self.__global_frequency))
                continue


            chain_height = blockchain_info["blocks"]
            bestblockhash = blockchain_info["bestblockhash"]


            try:
                mempool = self.__btc_rpc_connect.getrawmempool(True)

            except JSONRPCException as jsonrpc_err:
                log.exception("JSON-RPC `getrawmempool` error : ", exc_info=True)
                log.exception("Resuming operation, skipping current query...")
                time.sleep(int(self.__global_frequency))
                continue

            except Exception as sto_err:
                log.exception("Unexpected exception in JSON-RPC `getrawmempool`:", exc_info=True)
                log.exception("Resuming operation, skipping current query...")
                time.sleep(int(self.__global_frequency))
                continue


            # Runn bootstrapping code, if necessary
            if self.__bootstrap:
                self.__bootstrap = self.bootstrap_mempool_monitor(blockchain_info, mempool)
                
                time.sleep(int(self.__global_frequency))
                continue


            # Calculate mempool deltas (diff vs mempool at previous time)
            mempool_deltas = self.calculate_mempool_deltas(self.__mempool, mempool)


            try:
                # Dump mempool deltas....
                self.db.insert_mempool_txs(mempool_deltas["ADD"],
                                           self.__nr_ticks,
                                           chain_height,
                                           MODE_ADD)
                self.db.insert_mempool_txs(mempool_deltas["SUB"],
                                           self.__nr_ticks,
                                           chain_height,
                                           MODE_SUB)

            except Exception as sql_err:
                log.exception("SQL exception: {}".format(sql_err))

            # Log new block hash if detected
            if chain_height > self.__chain_height:
                log.info("Tick: {} - Chain Height: {}\nBest block: {}".format(self.__nr_ticks,
                                                                              chain_height,
                                                                              bestblockhash))
            # Else, send alive status if monitor still running
            elif self.__nr_ticks%10==0:
                log.info(f"Monitor running... current tick: {self.__nr_ticks}")


            self.__chain_height = chain_height
            self.__bestblockhash = bestblockhash

            self.__mempool = mempool

            self.__nr_ticks += 1


            time.sleep(int(self.__global_frequency))


    def bootstrap_mempool_monitor(self, blockchaininfo, mempool):
        """
        Bootstrap the mempool monitor - Only runs at start up, if monitor was never run before or if
        daemon got stopped and then restarted.

        Parameters
        ----------
        blockchaininfo : JSON object
            As returned by Bitcoin Core `getblockchaininfo` call.
        
        mempool : JSON object
            As returned by Bitcoin Core `getrawmempool` call

        Returns
        -------
        False : boolean
            Returns False upon successfull bootstrap!!!! 
        
        Examples
        --------
        To be used as
        >> self.__bootstrap = self.bootstrap_mempool_monitor 
        which allows a simple 
        >> if self.__bootstrap:
        """
        try:
            __nr_ticks = self.db.get_last_tick()
            
        except Exception as last_tick_err:
            log.exception("Exception in `get_last_tick`", exc_info=True)
            # Return True - i.e. monitor bootstrap failed and will need to be re-run
            return True

        log.info(f"Nr ticks in database: {__nr_ticks}")

        self.__chain_height = blockchaininfo["blocks"]
        self.__bestblockhash = blockchaininfo["bestblockhash"]
        self.__mempool = mempool

        # If database not empty, increase nr ticks by one, for first dump
        if __nr_ticks is not None:
            self.__nr_ticks += __nr_ticks+1

        # Dump mempool to database....
        try:
            self.db.insert_mempool_txs(mempool, self.__nr_ticks, self.__chain_height, MODE_INIT)
                
        except Exception as err:
            log.exception("SQL exception: ", exc_info=True)
            return True


        log.info("Tick: {} - Chain Height: {}\nBest block: {}".format(self.__nr_ticks,
                                                                      self.__chain_height,
                                                                      self.__bestblockhash))
        self.__nr_ticks += 1

        return False



    def calculate_mempool_deltas(self, mempool_t, mempool_tpone):
        """
        Calculate the difference between two mempool snapshot.

        Parameters
        ----------
        mempool_t : JSON object
            Mempool snapshot at time `t`. As returned by Bitcoin Core `getrawmempool` call.
        mempool_tpone : JSON object
            Mempool snapshot at time `t+1`. As returned by Bitcoin Core `getrawmempool` call.

        Returns
        -------
        {"ADD" : _mempool_add, "SUB" : _mempool_sub} : dict
            Dictionary that containes the new ADDitions and the SUBtractions to the most recent
            mempool, compared to the first one.
        """
        _txs_t = set(mempool_t)
        _txs_tpone = set(mempool_tpone)

        _delta_add = list(_txs_tpone - _txs_t)
        _delta_sub = list(_txs_t - _txs_tpone)

        _mempool_add = {txid:mempool_tpone[txid] for txid in _delta_add if txid in mempool_tpone}
        _mempool_sub = {txid:mempool_t[txid] for txid in _delta_sub if txid in mempool_t}


        return {"ADD" : _mempool_add,
                "SUB" : _mempool_sub}



    def process_new_block(self, best_block_hash):
        """
        Analyze new block, and detect which transactions from the mempool got confirmed

        TO DO: Unfinished function. Not needed for current code, might be completely unnecessary.
        """
        # _new_block_hash = self.__btc_rpc_connect.getblockhash(self.__chain_height)
        # print("New block detected - hash: {}".format(_new_block_hash))

        # NOTE!! .getblock() has THREE verbosity levels - 0, 1 and 2. Returns are:
        # 0 - String that is serialized, hex-encoded data for block 'hash'.
        # 1 - Object with information about block <hash>.
        # 2 - Object with information about block <hash> and information about each transaction.
        #
        # At first, we just need "1" - Get all tx ids is enough. That's because we assume the
        # confirmation fee is the same fee as it was seen in the last mempool snapshot, which is not
        # necessarily the case if RBF was used.
        #
        # (RBF transactions are monitored, but at this stage no final calculation is performed to
        # see if the fee changed between the last mempool snapshot and the block confirm.)
        #
        _new_block = self.__btc_rpc_connect.getblock(best_block_hash, 1) 
        _txs_in_block = set(_new_block['tx'])
        _txs_in_mempool = set(self.__mempool)
        _txs_not_in_mempool = _txs_in_block - _txs_in_mempool



