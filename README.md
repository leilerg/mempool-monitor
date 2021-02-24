Mempool monitor
==============

A script to monitor and store bitcoin mempool data in real time.


### What is Bitcoin?


Bitcoin is an experimental digital currency that enables instant payments to anyone, anywhere in the
world. Bitcoin uses peer-to-peer technology to operate with no central authority: managing
transactions and issuing money are carried out collectively by the network. Bitcoin Core is the name
of open source software which enables the use of this currency.

For further information see [bitcoincore.org](https://bitcoincore.ord).


### What is this script for?

Every bitcoin node maintains a local "memory pool" (mempool), i.e. a list of all the valid unconfirmed
transactions that have been broadcast. The the mempool composition changes primarily for two reasons:

* New transactions are added as users broadcast new transactions
* Once a block is confirmed, the transactions are removed from the mempool

This script stores the mempool data and allows to reconstruct the composition of the mempool over
time.


### Why is this useful?

Every valid transaction includes a fee to incentivize confirmation on the network. The bitcoin
netwok has a limited capacity to process transactions. If the network is running below or near
capacity, the transaction fee can be the smallest allowed and the user has a high degree of
confidence that it will get confirmed in the next block. However, when the network is running above
capacity, i.e. "blocks are full", users compete against for block inclusion through transaction
fees.

It is expected that the long term viability of bitcoin will require the network to operate in a
"full blocks" regime. This opens up the question of the appropriate level for the transaction
fee. This will clearly depend on the urgency of the transaction, with most urgent transactions
requiring the highest fees. Still, even for urgent transactions it is undesirable to overpay the
transaction fee. Stated differently, the following question arises:

*What is the minimum transaction fee I have to pay if I want to have high confidence that my
 transaction will be confirmed within N blocks?*


One approach to answer this question is to monitor the mempool evolution over time, which can be
done by using this script.


Requirements
------------

* [Bitcoin Core](https://github.com/bitcoin/bitcoin/) node up and running
* A SQL database, e.g. [MariaDB](https://mariadb.org/) or [MySQL](https://www.mysql.com/)


Both can be run either on a local machine or on a local network.



### Bitcoin Core

There are three requirements:

* Must have RPC credentials (*username* and *password*)
* The software must run as server and accept calls on some port (8332 is the default)
* The port must not be blocked


All these details must be entered in the ```config.ini``` file, ```[RPC]``` section.


### SQL database 

To set up the SQL database requirements requires a certain (minimal) familiarity with the RDBMS of
choice. (This has been tested with MariaDB.) No instructions are provided here on how to create
users, set privileges, create tables etc as it depends on the RDBMS.

All the below is required **before** running the script as the latter simply assumes it exists and
will fail if it doesn't.

#### Database structure


The database can have any name, and is a config setting in ```config.ini```. The structure of the
database must be as follows (assuming the database name is ```bitcoin_mempool```):

```
> DESCRIBE bitcoin_mempool;
+---------------------------+
| Tables_in_bitcoin_mempool |
+---------------------------+
| ancestor_descend          |
| raw_mempool               |
| unconfirmed_txs           |
+---------------------------+
3 rows in set


> DESCRIBE unconfirmed_txs;
+--------------------+-----------------------+------+-----+---------+----------------+
| Field              | Type                  | Null | Key | Default | Extra          |
+--------------------+-----------------------+------+-----+---------+----------------+
| nr                 | int(10) unsigned      | NO   | PRI | NULL    | auto_increment |
| ancestorcount      | smallint(5) unsigned  | YES  |     | NULL    |                |
| ancestorsize       | mediumint(8) unsigned | YES  |     | NULL    |                |
| bip125_replaceable | tinyint(1)            | YES  |     | NULL    |                |
| depends            | tinyint(1)            | YES  |     | NULL    |                |
| descendantcount    | smallint(5) unsigned  | YES  |     | NULL    |                |
| descendantsize     | mediumint(8) unsigned | YES  |     | NULL    |                |
| fees_base          | decimal(10,8)         | YES  |     | NULL    |                |
| fees_ancestor      | decimal(10,8)         | YES  |     | NULL    |                |
| fees_descendant    | decimal(10,8)         | YES  |     | NULL    |                |
| fees_modified      | decimal(10,8)         | YES  |     | NULL    |                |
| height             | mediumint(8) unsigned | YES  |     | NULL    |                |
| spentby            | tinyint(1)            | YES  |     | NULL    |                |
| time               | int(10) unsigned      | YES  |     | NULL    |                |
| vsize              | mediumint(8) unsigned | YES  |     | NULL    |                |
| weight             | mediumint(8) unsigned | YES  |     | NULL    |                |
| wtxid              | varchar(64)           | YES  |     | NULL    |                |
+--------------------+-----------------------+------+-----+---------+----------------+
17 rows in set 


> DESCRIBE raw_mempool;
+--------------+-----------------------+------+-----+---------+----------------+
| Field        | Type                  | Null | Key | Default | Extra          |
+--------------+-----------------------+------+-----+---------+----------------+
| nr           | int(10) unsigned      | NO   | PRI | NULL    | auto_increment |
| tick         | mediumint(8) unsigned | YES  | MUL | NULL    |                |
| txid         | varchar(64)           | YES  |     | NULL    |                |
| delta_mode   | varchar(4)            | YES  |     | NULL    |                |
| chain_height | mediumint(8) unsigned | YES  |     | NULL    |                |
+--------------+-----------------------+------+-----+---------+----------------+
5 rows in set


> DESCRIBE ancestor_descend;
+----------+-----------------------+------+-----+---------+-------+
| Field    | Type                  | Null | Key | Default | Extra |
+----------+-----------------------+------+-----+---------+-------+
| tick     | mediumint(8) unsigned | YES  | MUL | NULL    |       |
| txid     | varchar(64)           | YES  |     | NULL    |       |
| relation | varchar(8)            | YES  |     | NULL    |       |
| rel_txid | varchar(64)           | YES  |     | NULL    |       |
+----------+-----------------------+------+-----+---------+-------+
4 rows in set
```



#### Database user and privileges

It is also necessary to grant the required privileges to the user running the code. If we set up the
DB user as ```mempool```, we have:

```
> SHOW GRANTS for mempool;
+-----------------------------------------------------------------------------------------------------------------+
| Grants for mempool@%                                                                                            |
+-----------------------------------------------------------------------------------------------------------------+
| GRANT SELECT, INSERT ON *.* TO 'mempool'@'%' IDENTIFIED BY PASSWORD '*3227C632FDC00C215713058B9DA495B7D6BCCA6E' |
+-----------------------------------------------------------------------------------------------------------------+
```


Once the database has been created and a user has the required privileges, the information has to be
entered in the ```config.ini``` file.


Collecting data
---------------

If the above requirements are satisfied, to start collecting the data run simply:

```
python3 mpmonitor.py start
```

To stop the data collection:

```
python3 mpmonitor.py stop
```

Simple help available as:

```
python3 mpmonitor.py --help
```

