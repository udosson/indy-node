from indy_node.persistence.attribute_store import AttributeStore
from indy_node.server.pool_config import PoolConfig
from indy_node.server.request_handlers.action_req_handlers.pool_restart_handler import PoolRestartHandler
from indy_node.server.request_handlers.action_req_handlers.validator_info_handler import ValidatorInfoHandler
from indy_node.server.request_handlers.config_batch_handler import ConfigBatchHandler
from indy_node.server.request_handlers.config_req_handlers.auth_rule.auth_rule_handler import AuthRuleHandler
from indy_node.server.request_handlers.config_req_handlers.auth_rule.auth_rules_handler import AuthRulesHandler
from indy_node.server.request_handlers.config_req_handlers.pool_config_handler import PoolConfigHandler
from indy_node.server.request_handlers.config_req_handlers.pool_upgrade_handler import PoolUpgradeHandler
from indy_node.server.request_handlers.domain_req_handlers.idr_cache_nym_handler import IdrCacheNymHandler
from indy_node.server.request_handlers.idr_cache_batch_handler import IdrCacheBatchHandler
from indy_node.server.request_handlers.read_req_handlers.get_auth_rule_handler import GetAuthRuleHandler

from indy_node.server.request_handlers.domain_req_handlers.claim_def_handler import ClaimDefHandler
from indy_node.server.request_handlers.domain_req_handlers.revoc_reg_entry_handler import RevocRegEntryHandler
from indy_node.server.request_handlers.domain_req_handlers.schema_handler import SchemaHandler

from indy_node.server.request_handlers.domain_req_handlers.attribute_handler import AttributeHandler
from indy_node.server.request_handlers.domain_req_handlers.nym_handler import NymHandler
from indy_node.server.request_handlers.domain_req_handlers.revoc_reg_def_handler import RevocRegDefHandler

from indy_common.authorize.auth_map import auth_map, anyone_can_write_map

from common.serializers.serialization import domain_state_serializer
from indy_common.authorize.auth_constraints import ConstraintsSerializer
from indy_common.authorize.auth_request_validator import WriteRequestValidator
from indy_common.constants import CONFIG_LEDGER_ID
from indy_node.server.request_handlers.pool_req_handlers.node_handler import NodeHandler
from indy_node.server.request_handlers.read_req_handlers.get_attribute_handler import GetAttributeHandler
from indy_node.server.request_handlers.read_req_handlers.get_claim_def_handler import GetClaimDefHandler
from indy_node.server.request_handlers.read_req_handlers.get_nym_handler import GetNymHandler
from indy_node.server.request_handlers.read_req_handlers.get_revoc_reg_def_handler import GetRevocRegDefHandler
from indy_node.server.request_handlers.read_req_handlers.get_revoc_reg_delta_handler import GetRevocRegDeltaHandler
from indy_node.server.request_handlers.read_req_handlers.get_revoc_reg_handler import GetRevocRegHandler
from indy_node.server.request_handlers.read_req_handlers.get_schema_handler import GetSchemaHandler
from indy_node.server.restarter import Restarter
from indy_node.server.upgrader import Upgrader
from ledger.compact_merkle_tree import CompactMerkleTree
from ledger.genesis_txn.genesis_txn_initiator_from_file import GenesisTxnInitiatorFromFile
from plenum.common.constants import IDR_CACHE_LABEL, ATTRIB_LABEL, NODE_PRIMARY_STORAGE_SUFFIX
from plenum.common.ledger import Ledger
from plenum.persistence.storage import initStorage
from plenum.server.node_bootstrap import NodeBootstrap as PNodeBootstrap
from storage.helper import initKeyValueStorage


class NodeBootstrap(PNodeBootstrap):

    def init_idr_cache_storage(self):
        idr_cache = self.node.getIdrCache()
        self.node.db_manager.register_new_store(IDR_CACHE_LABEL, idr_cache)

    def init_attribute_store(self):
        return AttributeStore(
            initKeyValueStorage(
                self.node.config.attrStorage,
                self.node.dataLocation,
                self.node.config.attrDbName,
                db_config=self.node.config.db_attr_db_config)
        )

    def init_attribute_storage(self):
        # ToDo: refactor this on pluggable handlers integration phase
        if self.node.attributeStore is None:
            self.node.attributeStore = self.init_attribute_store()
        self.node.db_manager.register_new_store(ATTRIB_LABEL, self.node.attributeStore)

    def init_storages(self, storage=None):
        super().init_storages()
        self.init_idr_cache_storage()
        self.init_attribute_storage()

    def register_pool_req_handlers(self):
        node_handler = NodeHandler(self.node.db_manager,
                                   self.node.bls_bft.bls_crypto_verifier,
                                   self.node.write_req_validator)
        self.node.write_manager.register_req_handler(node_handler)

    def register_domain_req_handlers(self):
        # Read handlers
        get_nym_handler = GetNymHandler(database_manager=self.node.db_manager)
        get_attribute_handler = GetAttributeHandler(database_manager=self.node.db_manager)
        get_schema_handler = GetSchemaHandler(database_manager=self.node.db_manager)
        get_claim_def_handler = GetClaimDefHandler(database_manager=self.node.db_manager)
        get_revoc_reg_def_handler = GetRevocRegDefHandler(database_manager=self.node.db_manager)
        get_revoc_reg_handler = GetRevocRegHandler(database_manager=self.node.db_manager)
        get_revoc_reg_delta_handler = GetRevocRegDeltaHandler(database_manager=self.node.db_manager,
                                                              get_revocation_strategy=RevocRegDefHandler.get_revocation_strategy)
        # Write handlers
        nym_handler = NymHandler(database_manager=self.node.db_manager,
                                 write_req_validator=self.node.write_req_validator)
        attrib_handler = AttributeHandler(database_manager=self.node.db_manager)
        schema_handler = SchemaHandler(database_manager=self.node.db_manager,
                                       get_schema_handler=get_schema_handler,
                                       write_req_validator=self.node.write_req_validator)
        claim_def_handler = ClaimDefHandler(database_manager=self.node.db_manager,
                                            write_req_validator=self.node.write_req_validator)
        revoc_reg_def_handler = RevocRegDefHandler(database_manager=self.node.db_manager,
                                                   get_revoc_reg_def=get_revoc_reg_def_handler)
        revoc_reg_entry_handler = RevocRegEntryHandler(database_manager=self.node.db_manager,
                                                       get_revoc_reg_entry=get_revoc_reg_handler,
                                                       get_revocation_strategy=RevocRegDefHandler.get_revocation_strategy)
        # Register write handlers
        self.node.write_manager.register_req_handler(nym_handler)
        self.node.write_manager.register_req_handler(attrib_handler)
        self.node.write_manager.register_req_handler(schema_handler)
        self.node.write_manager.register_req_handler(claim_def_handler)
        self.node.write_manager.register_req_handler(revoc_reg_def_handler)
        self.node.write_manager.register_req_handler(revoc_reg_entry_handler)
        # Additional handler for idCache
        self.register_idr_cache_nym_handler()
        # Register read handlers
        self.node.read_manager.register_req_handler(get_nym_handler)
        self.node.read_manager.register_req_handler(get_attribute_handler)
        self.node.read_manager.register_req_handler(get_schema_handler)
        self.node.read_manager.register_req_handler(get_claim_def_handler)
        self.node.read_manager.register_req_handler(get_revoc_reg_def_handler)
        self.node.read_manager.register_req_handler(get_revoc_reg_handler)
        self.node.read_manager.register_req_handler(get_revoc_reg_delta_handler)

    def register_config_req_handlers(self):
        # Read handlers
        get_auth_rule_handler = GetAuthRuleHandler(database_manager=self.node.db_manager,
                                                   write_req_validator=self.node.write_req_validator)
        # Write handlers
        auth_rule_handler = AuthRuleHandler(database_manager=self.node.db_manager,
                                            write_req_validator=self.node.write_req_validator)
        auth_rules_handler = AuthRulesHandler(database_manager=self.node.db_manager,
                                              write_req_validator=self.node.write_req_validator)
        pool_config_handler = PoolConfigHandler(database_manager=self.node.db_manager,
                                                write_req_validator=self.node.write_req_validator,
                                                pool_config=self.node.poolCfg)
        pool_upgrade_handler = PoolUpgradeHandler(database_manager=self.node.db_manager,
                                                  upgrader=self.node.upgrader,
                                                  write_req_validator=self.node.write_req_validator,
                                                  pool_manager=self.node.poolManager)
        # Register write handlers
        self.node.write_manager.register_req_handler(auth_rule_handler)
        self.node.write_manager.register_req_handler(auth_rules_handler)
        self.node.write_manager.register_req_handler(pool_config_handler)
        self.node.write_manager.register_req_handler(pool_upgrade_handler)
        # Register read handlers
        self.node.read_manager.register_req_handler(get_auth_rule_handler)

    def register_action_req_handlers(self):
        # Action handlers
        pool_restart_handler = PoolRestartHandler(database_manager=self.node.db_manager,
                                                  write_req_validator=self.node.write_req_validator,
                                                  restarter=self.node.restarter)
        validator_info_handler = ValidatorInfoHandler(database_manager=self.node.db_manager,
                                                      write_req_validator=self.node.write_req_validator,
                                                      info_tool=self.node._info_tool)
        # Register action handlers
        self.node.action_manager.register_action_handler(pool_restart_handler)
        self.node.action_manager.register_action_handler(validator_info_handler)

    def register_domain_batch_handlers(self):
        super().register_domain_batch_handlers()
        self.register_idr_cache_batch_handler()

    def register_config_batch_handlers(self):
        config_batch_handler = ConfigBatchHandler(database_manager=self.node.db_manager,
                                                  upgrader=self.node.upgrader,
                                                  pool_config=self.node.poolCfg)
        self.node.write_manager.register_batch_handler(config_batch_handler)

    def register_idr_cache_nym_handler(self):
        idr_cache_nym_handler = IdrCacheNymHandler(database_manager=self.node.db_manager)
        self.node.write_manager.register_req_handler(idr_cache_nym_handler)

    def register_idr_cache_batch_handler(self):
        idr_cache_batch_handler = IdrCacheBatchHandler(database_manager=self.node.db_manager)
        self.node.write_manager.register_batch_handler(idr_cache_batch_handler)

    def init_pool_config(self):
        return PoolConfig(self.node.configLedger)

    def init_domain_ledger(self):
        """
        This is usually an implementation of Ledger
        """
        if self.node.config.primaryStorage is None:
            genesis_txn_initiator = GenesisTxnInitiatorFromFile(
                self.node.genesis_dir, self.node.config.domainTransactionsFile)
            return Ledger(
                CompactMerkleTree(
                    hashStore=self.node.getHashStore('domain')),
                dataDir=self.node.dataLocation,
                fileName=self.node.config.domainTransactionsFile,
                ensureDurability=self.node.config.EnsureLedgerDurability,
                genesis_txn_initiator=genesis_txn_initiator)
        else:
            return initStorage(self.node.config.primaryStorage,
                               name=self.node.name + NODE_PRIMARY_STORAGE_SUFFIX,
                               dataDir=self.node.dataLocation,
                               config=self.node.config)

    def init_upgrader(self):
        return Upgrader(self.node.id,
                        self.node.name,
                        self.node.dataLocation,
                        self.node.config,
                        self.node.configLedger,
                        actionFailedCallback=self.node.postConfigLedgerCaughtUp,
                        action_start_callback=self.node.notify_upgrade_start)

    def init_restarter(self):
        return Restarter(self.node.id,
                         self.node.name,
                         self.node.dataLocation,
                         self.node.config)

    def init_common_managers(self):
        super().init_common_managers()
        self.node.upgrader = self.init_upgrader()
        self.node.restarter = self.init_restarter()
        self.node.poolCfg = self.init_pool_config()

    def _init_write_request_validator(self):
        constraint_serializer = ConstraintsSerializer(domain_state_serializer)
        config_state = self.node.states[CONFIG_LEDGER_ID]
        self.node.write_req_validator = WriteRequestValidator(config=self.node.config,
                                                              auth_map=auth_map,
                                                              cache=self.node.getIdrCache(),
                                                              config_state=config_state,
                                                              state_serializer=constraint_serializer,
                                                              anyone_can_write_map=anyone_can_write_map,
                                                              metrics=self.node.metrics)
