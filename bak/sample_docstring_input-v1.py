def load_data():
    """Load the dataset.

    Return parsed records.
    """
    query = """
    SELECT * FROM records
    """
    return execute(query)
