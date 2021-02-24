"""
Module with various hard coded definitions.

Mot importantly, the structure of the database is defined here. If the database changes, this is
where the new steructure will have to be reflected.

# TO DO: Think if this, or at least part of it, could become a class.

Additionally, various strings are defined here for consistency across the code.
"""

NR                 = "nr"
TICK               = "tick"
CHAIN_HEIGHT       = "chain_height"
DELTA_MODE         = "delta_mode"

TXID               = "txid"
ANCESTORCOUNT      = "ancestorcount"
ANCESTORSIZE       = "ancestorsize"
BIP125             = "bip125"
REPLACEABLE        = "replaceable"
DEPENDS            = "depends"
DESCENDANTCOUNT    = "descendantcount"
DESCENDANTSIZE     = "descendantsize"
FEES               = "fees"
BASE               = "base"
ANCESTOR           = "ancestor"
DESCENDANT         = "descendant"
MODIFIED           = "modified"
HEIGHT             = "height"
SPENTBY            = "spentby"
TIME               = "time"
VSIZE              = "vsize"
WEIGHT             = "weight"
WTXID              = "wtxid"

DESCEND            = "descend"

FEES_BASE          = "_".join([FEES, BASE])
FEES_ANCESTOR      = "_".join([FEES, ANCESTOR])
FEES_DESCENDANT    = "_".join([FEES, DESCENDANT])
FEES_MODIFIED      = "_".join([FEES, MODIFIED])

RELATION           = "relation"
REL_TXID           = "_".join(["rel", TXID])


MODE_INIT          = "INIT"
MODE_ADD           = "ADD"
MODE_SUB           = "SUB"


UNCONFIRMED_TXS  = "unconfirmed_txs"
RAW_MEMPOOL      = "raw_mempool"
ANCESTOR_DESCEND = "_".join([ANCESTOR, DESCEND])



# IMPORTANT!!! The database has a field `bip125_replaceable`, but the corresponding key in bitcoin
# core is `bip125-replaceable` (underscore "_" vs hyphen "-").
# Thus creating two variables, one for DB structure definition and one for Bitcoin Core mempool
# objects 
DB_BIP125_REPLACEABLE = "_".join([BIP125, REPLACEABLE])
BC_BIP125_REPLACEABLE = "-".join([BIP125, REPLACEABLE])

DB_TABLES = {RAW_MEMPOOL      : [NR,                     # INTEGER UNSIGNED
                                 TICK,                   # MEDIUMINT UNSIGNED
                                 TXID,                   # VARCHAR(64)
                                 DELTA_MODE,             # VARCHAR(4)
                                 CHAIN_HEIGHT],          # MEDIUMINT UNSIGNED
             UNCONFIRMED_TXS  : [NR,                     # INTEGER UNSIGNED
                                 ANCESTORCOUNT,          # SMALLINT UNSIGNED
                                 ANCESTORSIZE,           # SMALLINT UNSIGNED
                                 DB_BIP125_REPLACEABLE,  # BOOLEAN/TINYINT
                                 DEPENDS,                # BOOLEAN/TINYINT
                                 DESCENDANTCOUNT,        # SMALLINT UNSIGNED
                                 DESCENDANTSIZE,         # SMALLINT UNSIGNED
                                 FEES_BASE,              # DECIMAL(10,8)
                                 FEES_ANCESTOR,          # DECIMAL(10,8)
                                 FEES_DESCENDANT,        # DECIMAL(10,8)
                                 FEES_MODIFIED,          # DECIMAL(10,8)
                                 HEIGHT,                 # MEDIUMINT UNSIGNED
                                 SPENTBY,                # BOOLEAN/TINYINT
                                 TIME,                   # INTEGER UNSIGNED
                                 VSIZE,                  # SMALLINT UNSIGNED
                                 WEIGHT,                 # SMALLINT UNSIGNED
                                 WTXID],                 # VARCHAR(64)
             ANCESTOR_DESCEND : [TICK,                   # MEDIUMINT UNSIGNED
                                 TXID,                   # VARCHAR(64)
                                 RELATION,               # VARCHAR(8)
                                 REL_TXID]}              # VARCHAR(64)

