import csv
import getopt
import json
import sys
from collections import defaultdict
from datetime import datetime

ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'


def parse_token_tx(tx_dict: dict, row: dict):
    tx = tx_dict[row['Txhash']]
    if tx.get('tokens') is None:
        tx['tokens'] = {}
    if tx['tokens'].get(row['TokenSymbol']) is None:
        tx['tokens'][row['TokenSymbol']] = []
    tx['tokens'][row['TokenSymbol']].append({
        'from': row['From'],
        'to': row['To'],
        'value': float(row['Value'].replace(',', ''))
    })
    return tx_dict


def format_join(tx_info: dict, pool_out: str, pool_address: str):
    action = {
        'pool_amount_out': pool_out,
        'tokens_in': {}
    }
    # 1 token other than the pool tokens means join_swap, else join with all tokens
    if (len(tx_info['tokens'].keys()) - 1) == 1:
        action['type'] = 'join_swap'
    else:
        action['type'] = 'join'
    for token in tx_info['tokens']:
        if token == 'BPT':
            continue
        token_tx = tx_info['tokens'][token][0]
        if token_tx['to'] == pool_address:
            action['tokens_in'][token] = token_tx['value']
    tx_info['action'] = action


def format_exit(tx_info: dict, pool_in: str, pool_address: str):
    action = {
        'pool_amount_in': pool_in,
        'tokens_out': {}
    }
    # 1 token other than the pool tokens means exit_swap, else join with all tokens
    if (len(tx_info['tokens'].keys()) - 1) == 1:
        action['type'] = 'exit_swap'
    else:
        action['type'] = 'exit'
    for token in tx_info['tokens']:
        if token == 'BPT':
            continue
        token_tx = tx_info['tokens'][token][0]
        if token_tx['from'] == pool_address:
            action['tokens_out'][token] = token_tx['value']
    tx_info['action'] = action


def format_swap(tx_info: dict, pool_address: str):
    action = {
        'type': 'swap'
    }
    for token in tx_info['tokens']:
        if token == 'BPT':
            continue
        token_tx = tx_info['tokens'][token][0]
        if token_tx['to'] == pool_address:
            action['token_in'] = token
            action['token_amount_in'] = token_tx['value']
        elif token_tx['from'] == pool_address:
            action['token_out'] = token
            action['token_amount_out'] = token_tx['value']
    tx_info['action'] = action


def classify_txs(txs: dict, pool_address: str) -> []:
    result_txs = []
    index = 0
    for tx_hash in txs:
        tx_info = txs[tx_hash]
        tx_info['index'] = index
        index += 1
        tokens = tx_info['tokens'].keys()
        if 'BPT' in tokens:
            # exit or join
            pool_token_operations = tx_info['tokens']['BPT']
            for bpt_tx in pool_token_operations:
                if bpt_tx['from'] == pool_address and bpt_tx['to'] != ZERO_ADDRESS:
                    format_join(tx_info, bpt_tx['value'], pool_address)
                    break
                elif bpt_tx['from'] == pool_address and bpt_tx['to'] == ZERO_ADDRESS:
                    format_exit(tx_info, bpt_tx['value'], pool_address)
                    break
        else:
            format_swap(tx_info, pool_address)
        result_txs.append(tx_info)
        result_txs[index-1]['tx_hash'] = tx_hash
    return result_txs


def get_grouped_txs(path: str) -> dict:
    with open(path, encoding='utf-8') as csvf:
        token_tx_list = csv.DictReader(csvf)
        result = defaultdict(lambda: False)
        for row in token_tx_list:
            if not result[row['Txhash']]:
                result[row['Txhash']] = {
                    'unixtimestamp': row['UnixTimestamp'],
                    'datetime': row['DateTime']
                }
            parse_token_tx(result, row)
        return result

def calculate_timesteps(token_txs):
    prev_tx_datetime = None
    for idx, token_tx in enumerate(token_txs):
        ts = int(token_tx['unixtimestamp'])
        tx_datetime = datetime.utcfromtimestamp(ts)
        if idx == 0:
            token_tx['timestep'] = 0
            prev_tx_datetime = tx_datetime
        else:
            timestep = (tx_datetime - prev_tx_datetime).total_seconds()
            token_tx['timestep'] = int(timestep)



def create_token_tx_file(input_file: str, output_file: str, pool_address: str):
    token_txs = classify_txs(txs=get_grouped_txs(input_file), pool_address=pool_address)
    calculate_timesteps(token_txs)
    # Serializing json
    json_object = json.dumps(token_txs, indent=4)

    # Writing to sample.json
    with open(output_file, "w") as outfile:
        outfile.write(json_object)


def main(argv):
    inputfile = ''
    outputfile = ''
    pool_address = None
    try:
        opts, args = getopt.getopt(argv, "hi:o:p:", ["ifile=", "ofile=", "paddress="])
    except getopt.GetoptError:
        print('convert_etherscan_csv.py -i <inputfile> -o <outputfile>  -p <pool_address>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('convert_etherscan_csv.py -i <inputfile> -o <outputfile> (optional) -p <pool_address>')
            sys.exit()
        elif opt in ("-p", "--paddress"):
            pool_address = arg.lower()
        elif opt in ("-i", "--ifile"):
            inputfile = arg
        elif opt in ("-o", "--ofile"):
            outputfile = arg
    if pool_address is None:
        raise Exception('pool address not provided')
    create_token_tx_file(input_file=inputfile, output_file=outputfile, pool_address=pool_address)


if __name__ == "__main__":
    main(sys.argv[1:])