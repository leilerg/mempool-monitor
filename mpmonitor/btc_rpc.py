from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException





class BitcoinRPC(object):

    def __init__(self, rpc_user, rpc_pass, rpc_host="localhost", rpc_port=8332, http_timeout=30):

        self.__rpc_user = rpc_user
        self.__rpc_pass = rpc_pass
        self.__rpc_host = rpc_host
        self.__rpc_port = rpc_port
        self.__http_timeout = http_timeout

        # self.rpc_connection = AuthServiceProxy("http://{}:{}@{}:{}".format(rpc_user, rpc_pass,
        #                                                                    rpc_host, rpc_port,
        #                                                                    timeout = http_timeout))


    def __getattr__(self, name):
        self.rpc_connection = AuthServiceProxy("http://{}:{}@{}:{}"
                                               .format(self.__rpc_user,
                                                       self.__rpc_pass,
                                                       self.__rpc_host,
                                                       self.__rpc_port,
                                                       timeout = self.__http_timeout))

        # return AuthServiceProxy(name)
        return self.rpc_connection.__getattr__(name)
