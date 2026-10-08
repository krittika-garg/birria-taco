#!/usr/bin/env python3
# This is a python script to load raw_data/states.csv


import csv
import os
import data.db_connect as dbc


def load_states(file_path):
    """
    Load states from a CSV file and return a list of dictionaries.

    Args:
        file_path (str): The path to the CSV file.
    """
    states = []
    with open(file_path, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            row['Latitude'] = float(row['Latitude'])
            row['Longitude'] = float(row['Longitude'])
            states.append(row)
    return states


def main():
    # accept the file path as an argument
    if len(os.sys.argv) > 1:
        file_path = os.sys.argv[1]
    else:
        print("USAGE: python load.py <path_to_states_csv>")
        exit(1)

    # Load states from the CSV file
    states = load_states(file_path)

    # Print the loaded states
    dbc.connect_db()
    for state in states:
        dbc.upsert('states', {'Abbrev': state['Abbrev']}, state)
    print(f'Imported {len(states)} state records.')


if __name__ == "__main__":
    main()
