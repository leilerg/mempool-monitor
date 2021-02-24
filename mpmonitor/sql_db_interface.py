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

    Parameters
    ----------
    sql_db : string
        Name of the database to connect to.
    sql_user : string
        Database user (with sufficent privileges) that will access the database.
    sql_pass : string
        Password to access the database `sql_db` for user `sql_user`.
    sql_host : string
        Host at which the database can be found.

    Example
    -------
    >> db_name = "mempool_monitor"
    >> db_user = "someuser"
    >> db_pass = "super complicated password not easy to guess"
    >> db_host = "127.0.0.1"
    >> db = SqlDbInterface(db_name, db_user, db_pass, db_host)
    >> db.get_last_tick()
    """

    def __init__(self, sql_db, sql_user, sql_pass, sql_host):
        """
        Initialize self.
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
        
        Parameters
        ----------
        verbose_mempool : dict/JSON object 
            As returned by Bitcoin Core method getrawmempool with verbosity set to true:
            `bitcoin-cli getrawmempool True` 
        tick : integer 
            Index that denotes at which time the mempool snapshot was taken.
        chain_height : integer
            The blochcain height for which we are storing data.
        delta_mode : string
            The "mode" these transaction should be considered: 
            "ADD" - These transactions have been added from the previous mempool snapshot
            "SUB" - These transactions have been removed from the previous mempool snapshot

        Returns
        -------
        True/False : Boolean
            True if successfull, False otherwise. On False will also raise an exception.
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
            return False
            # TO DO: Handle the error in more detail, depending on specific error

        return True


    def get_last_tick(self):
        """
        Method that retrieves the latest tick for which a snapshot has been taken from the
        database. If database is empty, returns None. 

        Parameters
        ----------
        None

        Returns
        -------
        _last_tick[0] : integer
            The last tick (id) available in the database. I.e. the integer ID of the number of
            records in the database.
            An exception is raised on failure.
        """

        _select_max_query = self.__sql_query_getmax(RAW_MEMPOOL, TICK)

        try:
            _last_tick = self.__sql_select(_select_max_query, "FETCHONE")

        except Exception as sql_err:
            log.exception(f"SQL exception: {sql_err}")
            raise

        return _last_tick[0]



    def __parse_mempool(self, _verbose_mempool, _tick, _chain_height, _delta_mode):
        """
        Method to parse `_verbose_mempool`

        Parameters
        ----------
        _verbose_mempool : dict/JSON object 
            As returned by Bitcoin Core method getrawmempool with verbosity set to true:
            `bitcoin-cli getrawmempool True` 
        _tick : integer 
            Index that denotes at which time the mempool snapshot was taken.
        _chain_height : integer
            The blochcain height for which we are storing data.
        _delta_mode : string
            The "mode" these transaction should be considered: 
            "ADD" - These transactions have been added from the previous mempool snapshot
            "SUB" - These transactions have been removed from the previous mempool snapshot

        Returns
        -------
        {UNCONFIRMED_TXS : [],
        RAW_MEMPOOL : [],
        ANCESTOR_DESCEND : []} : dict
            Dictionary with three lists containing "unconfirmed transactions", the "raw mempool" and
            "ancestors/descendants" info for specific transactions.
            The three keys correspond to the three tables of the database where the corresponding
            information is stored. 
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
        Parse single transaction `_txid` of `_verbose_mempool` for UNCONFIRMED_TXS table.

        Parameters
        ----------
        _txid : string 
            Transaction ID as constructed in Bitcoin Core
        _verbose_mempool : dict/JSON object 
            As returned by Bitcoin Core method getrawmempool with verbosity set to true:
            `bitcoin-cli getrawmempool True` 

        Returns
        -------
        tuple with parsed info : tuple
            The information is parsed and stored as a tuple.
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

        Parameters
        ----------
        txid - string
            Transaciton ID as constructed in Bitcoin Core
        verbose_mempool : dict/JSON object 
            As returned by Bitcoin Core method getrawmempool with verbosity set to true:
            `bitcoin-cli getrawmempool True` 
        tick - integer 
            Tick at which the mempool has been snapped

        Returns
        -------
        _ancestor_descend : list of tuples
            Contains the necessary info about ancestors and descendants of a transaction
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



    def __sql_query_insert(self, table, columns):
        """
        Constuctor of SQL query to use with `mysql.connector.cursor()`
        
        Parameters
        ----------
        table : string
            The neame of the table in which we to insert data
        columns : list of strings 
            The names of the columns in `table`

        Returns
        -------
        _sql_query_insert : string
            The SQL query to insert the data into the database.
        """
        fields="(" + ",".join(columns) + ")"
        filler = "(" + ",".join(len(columns)*["%s"]) + ")"


        return f"INSERT INTO {table} {fields} VALUES {filler};"


    def __sql_query_getmax(self, table, column):
        """
        SQL query constructor - Get MAX value from `column` in `table`

        Parameters
        ----------
        table : string
            Name of the table
        column : string
            The column from the table that we are interested in the max for.

        Returns
        -------
        _sql_query_getmax : string
            The SQL query to retrieve the max from a certain column
        """
        return f"SELECT MAX({column}) FROM {table};"


    def __sql_select(self, query, fetch="FETCHALL"):
        """
        Method to query database.

        Parameters
        ----------
        query : string
            The full SQL query required to retrieve the data. Must include the table name and all
            other conditions.
        fetch : string
            Regulates how many records to fetch. Default is "FETCHALL". If a single record is
            required, we must explicitly pass "FETCHONE" - Everything else will lead to the
            default. 
        
        Returns
        -------
        result : mysql.connector.connect.cursor.execute(query)
            Outcome of the query.
        """
        db = mysql.connector.connect(host = self.sql_host,
                                     user = self.sql_user,
                                     passwd = self.sql_pass,
                                     database = self.sql_db)
        cursor = db.cursor()

        cursor.execute(query)

        if fetch.upper()=="FETCHONE":
            result = cursor.fetchone()

        else:
            result = cursor.fetchall()


        return result


    
    def __sql_insert(self, _sql_query, _values, _insert_many=True):
        """
        Method to INSERT `values` into SQL `table` with `fields`

        Parameters
        ----------
        _sql_query : string
            The full SQL query required to insert data in a table. (Without the values.)
        _values : tuple
            Tuple of values to be inserted in the table.
        _insert_many : boolean
            If True, all values will be inserted at once - Default behaviour. If False, it will
            happen one-by-one. 

        Returns
        -------
        None

        TO DO: Address the return of the function. Should be something like True/False, depending on
        success or not.
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

        CURRENTLY UNUSED - POSSIBLY BROKEN - PROBABLY NOT NEEDED
        CURRENTLY UNUSED - POSSIBLY BROKEN - PROBABLY NOT NEEDED
        CURRENTLY UNUSED - POSSIBLY BROKEN - PROBABLY NOT NEEDED
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

        CURRENTLY UNUSED - POSSIBLY BROKEN - PROBABLY NOT NEEDED
        CURRENTLY UNUSED - POSSIBLY BROKEN - PROBABLY NOT NEEDED
        CURRENTLY UNUSED - POSSIBLY BROKEN - PROBABLY NOT NEEDED
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
