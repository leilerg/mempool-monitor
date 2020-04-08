"""
Main file for the app
"""
import os
import sys
import time
import configparser
import logging

from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

from mpmonitor.btc_rpc import BitcoinRPC
from mpmonitor.sql_db_interface import *


log = logging.getLogger(__name__)


def load_config():
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

    def __init__(self):
        try:
            app_config = load_config()
        except Exception as err:
            log.exception("Unhandled exception whilst loading config.\nException: {}".format(err))
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
            log.exception("Missing one or more mandatory config keys. Aborting.\n{}".format(k_err))
            print("ERROR - Missing one or more mandatory config keys. Aborting.\n{}".format(k_err))
            sys.exit()

        self.__bootstrap = True # Run bootstrapping code at first

        self.__btc_rpc_connect = None

        self.__nr_ticks = 0


        self.db = SqlDbInterface(sql_db, sql_user, sql_pass, sql_host)


    def run(self):
        """
        Main function of the monitor
        """


        while True:
            # Insantiate rpc interface
            self.__btc_rpc_connect = AuthServiceProxy("http://{}:{}@{}:{}"
                                                      .format(self.__rpc_user,
                                                              self.__rpc_pass,
                                                              self.__rpc_host,
                                                              self.__rpc_port,
                                                              timeout = self.__rpc_http_timeout))


            try:
                blockchain_info = self.__btc_rpc_connect.getblockchaininfo()


            except JSONRPCException as json_err:
                log.exception(json_err)
                log.info("Stopping daemon.")
                print("Connection error: {}".format(json_err))
                sys.exit()

            except Exception as sto_err:
                log.exception(sto_err)
                if self.__bootstrap:
                    log.info("Stopping daemon.")
                    print("ERROR: Socket problem. Stopping daemon.")
                    sys.exit()
                else:
                    time.sleep(int(self.__global_frequency))
                    continue

                

            
            chain_height = blockchain_info["blocks"]
            bestblockhash = blockchain_info["bestblockhash"]

            mempool = self.__btc_rpc_connect.getrawmempool(True)


            if self.__bootstrap:
                self.__chain_height = chain_height
                self.__bestblockhash = bestblockhash
                self.__mempool = mempool

                __nr_ticks = self.db.get_last_tick()

                log.info("Nr ticks in database: {}".format(__nr_ticks))

                # If database not empty, increase nr ticks by one, for first dump
                if __nr_ticks is not None:
                    self.__nr_ticks += __nr_ticks+1


                self.__bootstrap = False # Only need to bootstrap once...


                # Dump mempool to database....
                try:
                    self.db.insert_mempool_txs(mempool, self.__nr_ticks, chain_height, MODE_INIT)

                except Exception as err:
                    # print("Error in SQL INSERT: {}".format(err))
                    log.exception("SQL exception: {}".format(err))


                log.info("Tick: {} - Chain Height: {}\nBest block: {}".format(self.__nr_ticks,
                                                                              chain_height,
                                                                              bestblockhash))


                self.__nr_ticks += 1

                time.sleep(int(self.__global_frequency))
                continue



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


            if chain_height > self.__chain_height:
                log.info("Tick: {} - Chain Height: {}\nBest block: {}".format(self.__nr_ticks,
                                                                              chain_height,
                                                                              bestblockhash))


            self.__chain_height = chain_height
            self.__bestblockhash = bestblockhash

            self.__mempool = mempool

            self.__nr_ticks += 1


            time.sleep(int(self.__global_frequency))



    def calculate_mempool_deltas(self, mempool_t, mempool_tpone):
        """
        Calculate the difference between two mempool snapshot

        mempool_t     : Mempool snapshot at time `t`
        mempool_tpone : Mempool snapshot at time `t+1`
        """

        _txs_t = set(mempool_t)
        _txs_tpone = set(mempool_tpone)

        _delta_add = list(_txs_tpone - _txs_t)
        _delta_sub = list(_txs_t - _txs_tpone)

        _mempool_add = {txid:mempool_tpone[txid] for txid in _delta_add if txid in mempool_tpone}
        _mempool_sub = {txid:mempool_t[txid] for txid in _delta_sub if txid in mempool_t}


        return {"ADD" : _mempool_add,
                "SUB" : _mempool_sub}
        
        
        # print("DELTA ADD:\n{}".format(_delta_add))
        # print("\nDELTA SUB:\n{}".format(_delta_sub))

        



    def process_new_block(self, best_block_hash):
        """
        Analyze new block, and detect which transactions from the mempool got confirmed
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
        

        # pp(_new_block)





