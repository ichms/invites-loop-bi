import hmac
import hashlib

# uv pip install -e ./my_library

def generate_user_key(uuid_string, secret_salt):
	# Convert string variables to byte arrays
	uuid_bytes = str(uuid_string).encode('utf-8')
	salt_bytes = str(secret_salt).encode('utf-8')

	# Generate the deterministic HMAC-SHA256 hash
	hashed_result = hmac.new(salt_bytes, uuid_bytes, hashlib.sha256)

	return hashed_result.hexdigest()