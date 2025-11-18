import datetime
import hashlib
import json
from flask import Flask, request
import requests

app = Flask(__name__)

class Block:
    def __init__(self, index, transactions, timestamp, previous_hash, nonce=0):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce

    def compute_hash(self):
        block_string = json.dumps(self.__dict__, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()


class Blockchain:
    difficulty = 2

    def __init__(self):
        self.unconfirmed_transactions = []
        self.chain = []
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = Block(0, [], str(datetime.datetime.now()), "0")
        genesis_block.hash = genesis_block.compute_hash()
        self.chain.append(genesis_block)

    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, block):
        block.nonce = 0
        computed_hash = block.compute_hash()
        while not computed_hash.startswith('0' * Blockchain.difficulty):
            block.nonce += 1
            computed_hash = block.compute_hash()
        return computed_hash

    def add_block(self, block, proof):
        previous_hash = self.last_block.hash
        if previous_hash != block.previous_hash:
            return False
        if not self.is_valid_proof(block, proof):
            return False
        block.hash = proof
        self.chain.append(block)
        return True

    def is_valid_proof(self, block, block_hash):
        return (block_hash.startswith('0' * Blockchain.difficulty)
                and block_hash == block.compute_hash())

    def add_new_transaction(self, transaction):
        self.unconfirmed_transactions.append(transaction)

    def mine(self):
        if not self.unconfirmed_transactions:
            return False

        last_block = self.last_block
        new_block = Block(index=last_block.index + 1,
                          transactions=self.unconfirmed_transactions,
                          timestamp=str(datetime.datetime.now()),
                          previous_hash=last_block.hash)

        proof = self.proof_of_work(new_block)
        self.add_block(new_block, proof)
        self.unconfirmed_transactions = []
        return new_block.index


blockchain = Blockchain()
peers = set()


@app.route('/new_transaction', methods=['POST'])
def new_transaction():
    tx_data = request.get_json()
    required_fields = ["author", "content"]
    for field in required_fields:
        if not tx_data.get(field):
            return "Invalid transaction", 404

    tx_data["timestamp"] = str(datetime.datetime.now())
    blockchain.add_new_transaction(tx_data)
    return "Success", 201


@app.route('/chain', methods=['GET'])
def get_chain():
    chain_data = []
    for block in blockchain.chain:
        chain_data.append(block.__dict__)

    return json.dumps({
        "length": len(chain_data),
        "chain": chain_data,
        "peers": list(peers)
    })


@app.route('/mine', methods=['GET'])
def mine_unconfirmed_transactions():
    result = blockchain.mine()
    if not result:
        return "No transactions to mine"

    announce_new_block(blockchain.last_block)
    return f"Block #{result} mined"


@app.route('/pending_tx')
def pending_tx():
    return json.dumps(blockchain.unconfirmed_transactions)


# ========== MULTI-NODO: REGISTRO DE PARES ==========

@app.route('/register_node', methods=['POST'])
def register_new_peer():
    node_address = request.get_json()["node"]
    if not node_address:
        return "Invalid data", 400

    peers.add(node_address)
    return get_chain()


@app.route('/register_with_existing_node', methods=['POST'])
def register_with_existing_node():
    node_address = request.get_json()["node_address"]
    if not node_address:
        return "Invalid data", 400

    data = {"node": request.host_url[:-1]}
    headers = {'Content-Type': 'application/json'}

    response = requests.post(node_address + "/register_node",
                             data=json.dumps(data), headers=headers)

    global blockchain
    global peers
    if response.status_code == 200:
        chain_dump = json.loads(response.content)
        blockchain = create_chain_from_dump(chain_dump["chain"])
        peers.update(chain_dump["peers"])
        return "Registration successful", 200
    return "Registration failed", 400


def create_chain_from_dump(chain_dump):
    blockchain = Blockchain()
    blockchain.chain = []
    for block_data in chain_dump:
        block = Block(
            block_data["index"],
            block_data["transactions"],
            block_data["timestamp"],
            block_data["previous_hash"],
            block_data["nonce"]
        )
        block.hash = block_data["hash"]
        blockchain.chain.append(block)

    return blockchain


# ============ DIFUSIÓN DE BLOQUES ===============

@app.route('/add_block', methods=['POST'])
def add_block():
    block_data = request.get_json()
    block = Block(block_data["index"],
                  block_data["transactions"],
                  block_data["timestamp"],
                  block_data["previous_hash"],
                  block_data["nonce"])
    proof = block_data['hash']

    added = blockchain.add_block(block, proof)
    if not added:
        return "Block rejected", 400

    return "Block added", 201


def announce_new_block(block):
    for peer in peers:
        url = peer + "/add_block"
        headers = {'Content-Type': 'application/json'}
        requests.post(url, data=json.dumps(block.__dict__), headers=headers)


# ============ CONSENSO =============

@app.route('/consensus')
def consensus():
    global blockchain

    longest_chain = None
    current_len = len(blockchain.chain)

    for peer in peers:
        response = requests.get(peer + "/chain")
        if response.status_code == 200:
            length = json.loads(response.content)["length"]
            chain = json.loads(response.content)["chain"]
            if length > current_len and is_valid_chain(chain):
                current_len = length
                longest_chain = chain

    if longest_chain:
        blockchain = create_chain_from_dump(longest_chain)
        return "Chain replaced", 200

    return "Chain is authoritative", 200


def is_valid_chain(chain):
    previous_hash = "0"
    for block in chain:
        block_obj = Block(
            block["index"],
            block["transactions"],
            block["timestamp"],
            block["previous_hash"],
            block["nonce"]
        )
        if block_obj.previous_hash != previous_hash:
            return False
        if block["hash"] != block_obj.compute_hash():
            return False
        previous_hash = block["hash"]
    return True


# ============ EJECUCIÓN DEL SERVIDOR =============

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default=8000)
    args = parser.parse_args()
    port = int(args.port)
    app.run(host='0.0.0.0', port=port)


