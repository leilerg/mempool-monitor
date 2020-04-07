"""
This implements an interface to a SQL database for the dumping/reconstructing the Bitcoin mempool.
"""
import logging

import mysql.connector
from mysql.connector import errorcode

from mpmonitor.sql_db_structure import *


log = logging.getLogger(__file__)


class SqlDbInterface(object):
    """
    Class that implements an interface to a SQL database. Uses the `mysql` package and automatically
    constructs the SQL queries.
    """

    def __init__(self, sql_db, sql_user, sql_pass, sql_host):
        """
        Class init
        """
        self.sql_db   = sql_db
        self.sql_user = sql_user
        self.sql_pass = sql_pass
        self.sql_host = sql_host

        self.sql_query_insert = {}
        
        for table, fields in DB_TABLES.items():
            self.sql_query_insert[table] = self.__sql_query_insert(table, fields)



    def insert_mempool_txs(self, verbose_mempool, tick, chain_height, delta_mode):
        """
        Main method of the class - Inserts the transactions from the `verbose_mempool` into the
        database
        
        verbose_mempool - Dict/JSON object as returned by Bitcoin Core method getrawmempool with
        verbosity set to true: `bitcoin-cli getrawmempool True`
        tick - Integer - Index that denotes at which time the mempool snapshot was taken
        """

        response = self.__parse_mempool(verbose_mempool, tick, chain_height, delta_mode)
        
        unconfirmed_txs_values  = response[UNCONFIRMED_TXS]
        raw_mempool_values      = response[RAW_MEMPOOL]
        ancestor_descend_values = response[ANCESTOR_DESCEND]


        try:
            self.__sql_insert(self.sql_query_insert[UNCONFIRMED_TXS], unconfirmed_txs_values)
            self.__sql_insert(self.sql_query_insert[RAW_MEMPOOL], raw_mempool_values)
            self.__sql_insert(self.sql_query_insert[ANCESTOR_DESCEND], ancestor_descend_values)

        except Exception as sql_err:
            log.exception("SQL exception: {}".format(sql_err))
            # TO DO: Hadnle the error in more detail, depending on specific error

        return True


    def get_last_tick(self):
        """
        Method that retrieves the latest tick for which a snapshot has been taken from the
        database. If database is empty, returns None. 
        """

        _select_max_query = self.__sql_query_getmax(RAW_MEMPOOL, TICK)

        try:
            _last_tick = self.__sql_select(_select_max_query, "FETCHONE")

        except Exception as sql_err:
            log.exception("SQL exception: {}".format(sql_err))
            _last_tick[0] = None

        return _last_tick[0]




    def __parse_mempool(self, _verbose_mempool, _tick, _chain_height, _delta_mode):
        """
        Method to parse `_verbose_mempool`

        _verbose_mempool - Dict/JSON object as returned by Bitcoin Core method getrawmempool with
        verbosity set to true: `bitcoin-cli getrawmempool True`
        _tick - Integer - Index that denotes at which time the mempool snapshot was taken
        """


        _unconfirmed_txs_values  = []
        _raw_mempool_values      = []
        _ancestor_descend_values = []

        # Process one tx at a time to ensure the order is preserved across various tables
        for txid in _verbose_mempool:
            _unconfirmed_tx = self.__parse_unconfirmed_txs(txid, _verbose_mempool)
            _raw_mempool    = tuple([None, _tick, txid, _delta_mode, _chain_height])
            _ancestor_descend = []

            # Only insert ancestors/descendants for 'INIT' and 'ADD' modes (for 'SUB' is redundant,
            # these are previously existing transactions that are being removed from the mempool)
            _txs_has_ancestor_depends = (_verbose_mempool[txid][ANCESTORCOUNT]>1 or \
                                         _verbose_mempool[txid][DESCENDANTCOUNT]>1)

            if _delta_mode != MODE_SUB and _txs_has_ancestor_depends:
                _ancestor_descend = self.__parse_ancestor_descend(txid,_verbose_mempool, _tick)


            _unconfirmed_txs_values.append(_unconfirmed_tx)
            _raw_mempool_values.append(_raw_mempool)
            _ancestor_descend_values.extend(_ancestor_descend)


        return {UNCONFIRMED_TXS  : _unconfirmed_txs_values,
                RAW_MEMPOOL      : _raw_mempool_values,
                ANCESTOR_DESCEND : _ancestor_descend_values}



    def __parse_unconfirmed_txs(self, _txid, _verbose_mempool):
        """
        Method to parse single transaction `_txid` of `_verbose_mempool` for UNCONFIRMED_TXS table

        _txid - Transaciton ID as constructed in Bitcoin Core
        _verbose_mempool - Dict/JSON object as returned by Bitcoin Core method getrawmempool with
        verbosity set to true: `bitcoin-cli getrawmempool True`
        """

        ancestorcount      = _verbose_mempool[_txid][ANCESTORCOUNT]
        ancestorsize       = _verbose_mempool[_txid][ANCESTORSIZE]
        bip125_replaceable = _verbose_mempool[_txid][BC_BIP125_REPLACEABLE]
        depends            = bool(ancestorcount-1)  # Ancestor count>1 imples there's depends
        descendantcount    = _verbose_mempool[_txid][DESCENDANTCOUNT]
        descendantsize     = _verbose_mempool[_txid][DESCENDANTSIZE]
        fees_base          = _verbose_mempool[_txid][FEES][BASE]
        fees_ancestor      = _verbose_mempool[_txid][FEES][ANCESTOR]
        fees_descendant    = _verbose_mempool[_txid][FEES][DESCENDANT]
        fees_modified      = _verbose_mempool[_txid][FEES][MODIFIED]
        height             = _verbose_mempool[_txid][HEIGHT]
        spentby            = bool(descendantcount-1) # Descend count >1 implies children txs
        time               = _verbose_mempool[_txid][TIME]
        vsize              = _verbose_mempool[_txid][VSIZE]
        weight             = _verbose_mempool[_txid][WEIGHT]
        wtxid              = _verbose_mempool[_txid][WTXID]
            
            
        return tuple([None,
                      ancestorcount,
                      ancestorsize,
                      bip125_replaceable,
                      depends,
                      descendantcount,
                      descendantsize,
                      fees_base,
                      fees_ancestor,
                      fees_descendant,
                      fees_modified,
                      height,
                      spentby,
                      time,
                      vsize,
                      weight,
                      wtxid])



    def __parse_ancestor_descend(self, txid, verbose_mempool, tick):
        """
        Method to parse the ancestors and descendants of a mempool transaction.

        txid - Transaciton ID as constructed in Bitcoin Core
        verbose_mempool - Dict/JSON object as returned by Bitcoin Core method getrawmempool with
        verbosity set to true: `bitcoin-cli getrawmempool True`
        tick - Tick at which the mempool has been snapped
        """

        _ancestor_descend = []
        
        if verbose_mempool[txid][ANCESTORCOUNT]>1:
            for _ancestor in verbose_mempool[txid][DEPENDS]:
                _ancestor_descend.append(tuple([tick, txid, ANCESTOR, _ancestor]))


        if verbose_mempool[txid][DESCENDANTCOUNT]>1:
            for _descendant in verbose_mempool[txid][SPENTBY]:
                _ancestor_descend.append(tuple([tick, txid, DESCEND, _descendant]))


        return _ancestor_descend


    # def __parse_raw_mempool(self, _txid, _verbose_mempool, _tick, _chain_height, _mode):
    #     """
    #     Method to parse `_verbose_mempool` for RAW_MEMPOOL table

    #     _verbose_mempool - Dict/JSON object as returned by Bitcoin Core method getrawmempool with
    #     verbosity set to true: `bitcoin-cli getrawmempool True`
    #     """

    #     _raw_mempool = []
    #     # Parsing for table `unconfirmed_txs`
    #     for txid in _verbose_mempool:
    #         _raw_mempool.append(tuple([None, _tick, txid, _mode, _chain_height]))


    #     return  _raw_mempool






    def __sql_query_insert(self, table, table_fields):
        """
        Constuctor of SQL query to use with `mysql.connector.cursor()`
        """

        fields="(" + ",".join(table_fields) + ")"
        filler = "(" + ",".join(len(table_fields)*["%s"]) + ")"

        _sql_query_insert = "INSERT INTO {} {} VALUES {};".format(table, fields, filler)
    
        return _sql_query_insert


    def __sql_query_getmax(self, table, column):
        """
        SQL query constructor - Get MAX value from `column` in `table`
        """

        _sql_query_getmax = "SELECT MAX({}) FROM {};".format(column, table)

        return _sql_query_getmax




    def __sql_select(self, query, fetch="FETCHALL"):
        """
        Method to SELECT data from 
        """
        db = mysql.connector.connect(host = self.sql_host,
                                     user = self.sql_user,
                                     passwd = self.sql_pass,
                                     database = self.sql_db)

        cursor = db.cursor()

        cursor.execute(query)

        if fetch=="FETCHONE":
            result = cursor.fetchone()

        else:
            result = cursor.fetchall()


        return result


    
    def __sql_insert(self, _sql_query, _values, _insert_many=True):
        """
        Method to INSERT `values` into SQL `table` with `fields` - Single row
        """
        db = mysql.connector.connect(host = self.sql_host,
                                     user = self.sql_user,
                                     passwd = self.sql_pass,
                                     database = self.sql_db)

        cursor = db.cursor()


        if _insert_many:
            cursor.executemany(_sql_query, _values)

        else:
            cursor.execute(_sql_query, _values)


        db.commit()

        cursor.close()
        db.close()



    def __sql_insert_single(self, table, values):
        """
        Method to INSERT `values` into SQL `table` with `fields` - Single row
        """
        db = mysql.connector.connect(host = self.sql_host,
                                     user = self.sql_user,
                                     passwd = self.sql_pass,
                                     database = self.sql_db)

        cursor = db.cursor()

        cursor.execute(self.sql_query_insert[table], values)

        db.commit()

        cursor.close()
        db.close()



    def __sql_insert_many(self, table, values):
        """
        Method to INSERT `values` into SQL `table` with `fields` - MANY rows
        """
        db = mysql.connector.connect(host = self.sql_host,
                                     user = self.sql_user,
                                     passwd = self.sql_pass,
                                     database = self.sql_db)

        cursor = db.cursor()

        cursor.executemany(self.sql_query_insert[table], values)

        db.commit()

        cursor.close()
        db.close()



# class SqlDbInterface(object):
#     """
#     Class that implements an interface to a SQL database. Uses the `mysql` package and automatically
#     constructs the SQL queries.
#     """

#     def __init__(self, sql_db, sql_user, sql_pass, sql_host):
#         """
#         Class init
#         """
#         self.sql_db   = sql_db
#         self.sql_user = sql_user
#         self.sql_pass = sql_pass
#         self.sql_host = sql_host

#         self.sql_query_insert = {}
        
#         for table, fields in DB_TABLES.items():
#             self.sql_query_insert[table] = self.__sql_query_insert(table, fields)

        

#     def insert_mempool_txs(self, verbose_mempool, tick):
#         """
#         Main method of the class - Inserts the transactions from the `verbose_mempool` into the
#         database
        
#         verbose_mempool - Dict/JSON object as returned by Bitcoin Core method getrawmempool with
#         verbosity set to true: `bitcoin-cli getrawmempool True`
#         tick - Integer - Index that denotes at which time the mempool snapshot was taken
#         """

#         response = self.__parse_mempool(verbose_mempool, tick)
        
#         unconfirmed_txs_values = response[UNCONFIRMED_TXS]


#         self.__sql_insert_many(UNCONFIRMED_TXS, unconfirmed_txs_values)


        
#         return unconfirmed_txs_values



#     def __parse_mempool(self, _verbose_mempool, _snapshot_t):
#         """
#         Method to parse `_verbose_mempool`

#         _verbose_mempool - Dict/JSON object as returned by Bitcoin Core method getrawmempool with
#         verbosity set to true: `bitcoin-cli getrawmempool True`
#         _tick - Integer - Index that denotes at which time the mempool snapshot was taken
#         """

        
#         _unconfirmed_txs_values = []
#         _single_tx_values = []
#         # Parsing for table `unconfirmed_txs`
#         for txid in _verbose_mempool:

#             tick               = _tick
            
#             ancestorcount      = _verbose_mempool[txid][ANCESTORCOUNT]
#             ancestorsize       = _verbose_mempool[txid][ANCESTORSIZE]
#             bip125_replaceable = _verbose_mempool[txid][BC_BIP125_REPLACEABLE]
#             depends            = bool(ancestorcount-1)  # Ancestor count>1 imples there's depends
#             descendantcount    = _verbose_mempool[txid][DESCENDANTCOUNT]
#             descendantsize     = _verbose_mempool[txid][DESCENDANTSIZE]
#             fees_base          = _verbose_mempool[txid][FEES][BASE]
#             fees_ancestor      = _verbose_mempool[txid][FEES][ANCESTOR]
#             fees_descendant    = _verbose_mempool[txid][FEES][DESCENDANT]
#             fees_modified      = _verbose_mempool[txid][FEES][MODIFIED]
#             height             = _verbose_mempool[txid][HEIGHT]
#             spentby            = bool(descendantcount-1) # Descend count >1 implies children txs
#             time               = _verbose_mempool[txid][TIME]
#             vsize              = _verbose_mempool[txid][VSIZE]
#             weight             = _verbose_mempool[txid][WEIGHT]
#             wtxid              = _verbose_mempool[txid][WTXID]

#             _single_tx_values = [tick,
#                                  txid,
#                                  ancestorcount,
#                                  ancestorsize,
#                                  bip125_replaceable,
#                                  depends,
#                                  descendantcount,
#                                  descendantsize,
#                                  fees_base,
#                                  fees_ancestor,
#                                  fees_descendant,
#                                  fees_modified,
#                                  height,
#                                  spentby,
#                                  time,
#                                  vsize,
#                                  weight,
#                                  wtxid]

#             _unconfirmed_txs_values.append(tuple(_single_tx_values))

#         return {UNCONFIRMED_TXS : _unconfirmed_txs_values}


    
#     def __sql_query_insert(self, table, table_fields):
#         """
#         Constuctor of SQL query to use with `mysql.connector.cursor()`
#         """

#         fields="(" + ",".join(table_fields) + ")"
#         filler = "(" + ",".join(len(table_fields)*["%s"]) + ")"

#         _sql_query_insert = "INSERT INTO {} {} VALUES {};".format(table, fields, filler)
    
#         return _sql_query_insert



#     def __sql_insert(self, table, values):
#         """
#         Method to INSERT `values` into SQL `table` with `fields` - Single row
#         """
#         db = mysql.connector.connect(host = self.sql_host,
#                                      user = self.sql_user,
#                                      passwd = self.sql_pass,
#                                      database = self.sql_db)

#         cursor = db.cursor()

#         cursor.execute(self.sql_query_insert[table], values)

#         db.commit()

#         cursor.close()
#         db.close()






#     def __sql_insert_single(self, table, values):
#         """
#         Method to INSERT `values` into SQL `table` with `fields` - Single row
#         """
#         db = mysql.connector.connect(host = self.sql_host,
#                                      user = self.sql_user,
#                                      passwd = self.sql_pass,
#                                      database = self.sql_db)

#         cursor = db.cursor()

#         cursor.execute(self.sql_query_insert[table], values)

#         db.commit()

#         cursor.close()
#         db.close()



#     def __sql_insert_many(self, table, values):
#         """
#         Method to INSERT `values` into SQL `table` with `fields` - MANY rows
#         """
#         db = mysql.connector.connect(host = self.sql_host,
#                                      user = self.sql_user,
#                                      passwd = self.sql_pass,
#                                      database = self.sql_db)

#         cursor = db.cursor()

#         try:
#             cursor.executemany(self.sql_query_insert[table], values)
#         except Exception as sql_err:
#             print("Problems with insert many: {}\n".format(sql_err))
#             pp(values[50:55])


#         db.commit()

#         cursor.close()
#         db.close()







