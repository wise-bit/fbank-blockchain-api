import os
import sys
import time
import json
import hashlib
import threading
import signal
from flask import Flask, request, jsonify
from flask_cors import CORS

shutdown_event = threading.Event()  # global thread variable


class Transaction:
    def __init__(self, sender, recipient, amount):
        self.sender = sender
        self.recipient = recipient
        self.amount = amount

    def to_dict(self):
        return self.__dict__


class Block:
    def __init__(self, index, timestamp, transactions, proof, previous_hash):
        self.index = index
        self.timestamp = timestamp
        self.transactions = transactions  # List of transactions
        self.proof = proof
        self.previous_hash = previous_hash

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "proof": self.proof,
            "previous_hash": self.previous_hash,
        }


class Blockchain:
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.load_from_file()

        if len(self.chain) == 0:
            self.new_block(previous_hash="1", proof=100)  # Genesis block

    def new_block(self, proof, previous_hash=None):
        block = Block(
            index=len(self.chain) + 1,
            timestamp=time.time(),
            transactions=self.current_transactions,
            proof=proof,
            previous_hash=previous_hash or self.hash(self.chain[-1]),
        )
        self.current_transactions = []
        self.chain.append(block)
        self.save_to_file()
        return block

    def new_transaction(self, sender, recipient, amount):
        transaction = Transaction(sender, recipient, amount)
        self.current_transactions.append(transaction)
        self.save_to_file()
        return self.last_block.index + 1

    @property
    def last_block(self):
        return self.chain[-1]

    @staticmethod
    def hash(block):
        block_string = json.dumps(block.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self, last_proof):
        proof = 0
        while not self.valid_proof(last_proof, proof):
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        guess = f"{last_proof}{proof}".encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def save_to_file(self, filename="blockchain.json"):
        with open(filename, "w") as f:
            chain_data = [block.to_dict() for block in self.chain]
            json.dump(chain_data, f, indent=4)

    def dump_all_to_file(self, filename="transaction_dump.json"):
        with open(filename, "w") as f:
            dump_data = self.get_full_transaction_logs()
            json.dump(dump_data, f, indent=4)

    def load_from_file(self, filename="blockchain.json"):
        if os.path.exists(filename):
            with open(filename, "r") as f:
                chain_data = json.load(f)
                for block_data in chain_data:
                    block = Block(
                        index=block_data["index"],
                        timestamp=block_data["timestamp"],
                        transactions=[
                            Transaction(**tx) for tx in block_data["transactions"]
                        ],
                        proof=block_data["proof"],
                        previous_hash=block_data["previous_hash"],
                    )
                    self.chain.append(block)

    def get_confirmed_transactions(self):
        transactions = [
            tx.to_dict() for block in self.chain for tx in block.transactions
        ]
        return transactions

    def get_pending_transactions(self):
        transactions = [tx.to_dict() for tx in self.current_transactions]
        return transactions

    def get_full_transaction_logs(self):
        return {
            "pending": self.get_pending_transactions(),
            "confirmed": self.get_confirmed_transactions(),
        }


# Flask setup

app = Flask(__name__)
CORS(app)

blockchain = Blockchain()


@app.route("/mine", methods=["POST"])
def mine_block():
    values = request.get_json()
    required = ["name"]
    if not all(k in values for k in required):
        return "Missing values", 400

    last_block = blockchain.last_block
    last_proof = last_block.proof
    proof = blockchain.proof_of_work(last_proof)

    blockchain.new_transaction(
        sender="fbank_blockchain", recipient=values["name"], amount=1
    )

    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        "message": "New Block Forged",
        "index": block.index,
        "transactions": [tx.to_dict() for tx in block.transactions],
        "proof": block.proof,
        "previous_hash": block.previous_hash,
    }
    return jsonify(response), 201


@app.route("/transactions/new", methods=["POST"])
def new_transaction():
    values = request.get_json()
    required = ["sender", "recipient", "amount"]
    if not all(k in values for k in required):
        return "Missing values", 400

    index = blockchain.new_transaction(
        values["sender"], values["recipient"], values["amount"]
    )

    response = {"message": f"Transaction will be added to Block {index}"}
    return jsonify(response), 201


@app.route("/transactions", methods=["GET"])
def get_transactions():
    response = blockchain.get_full_transaction_logs()
    return jsonify(response), 200


@app.route("/chain", methods=["GET"])
def full_chain():
    response = {
        "chain": [block.to_dict() for block in blockchain.chain],
        "length": len(blockchain.chain),
    }
    return jsonify(response), 200


def save_periodically(interval=1800):
    while not shutdown_event.is_set():
        time.sleep(interval)
        if shutdown_event.is_set():
            break
        blockchain.save_to_file()
        blockchain.dump_all_to_file()


def signal_handler(sig, frame):
    print("Signal received, shutting down gracefully...")
    blockchain.save_to_file()
    blockchain.dump_all_to_file()
    shutdown_event.set()
    thread.join(timeout=2)
    print("Shutdown complete.")
    sys.exit(0)


# Register signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Periodic saving in background
thread = threading.Thread(target=save_periodically, daemon=True)
thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
