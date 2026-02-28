"""
Calculator module for basic math operations
"""

def add_numbers(x, y):
    result = x + y
    return result

def calculate_average(numbers):
    sum = 0
    for num in numbers:
        sum = sum + num
    return sum / len(numbers)

def process_data(data):
    results = []
    for item in data:
        if item > 0:
            results.append(item * 2)
    return results

def format_name(first, last):
    return first + " " + last
