"""Sample application for testing auto-fix agent"""

def process_users(users):
    result = []
    for user in users:
        result.append(user.name)
    return result

def calculate_discount(price, discount_percent):
    discount = price * discount_percent / 100
    final_price = price - discount
    return final_price

class UserManager:
    def __init__(self):
        self.users = []

    def add_user(self, name, email):
        user = {"name": name, "email": email}
        self.users.append(user)
        return user

    def find_user(self, name):
        for user in self.users:
            if user["name"] == name:
                return user
        return None

def validate_email(email):
    if "@" in email and "." in email:
        return True
    else:
        return False

def get_user_names(users):
    names = []
    for user in users:
        names.append(user['name'])
    return names
