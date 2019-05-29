Starlette includes several password hashing classes that let you
create and check passwords.


## PasswordChecker

Among these classes is a special class `PasswordChecker`.
It is intended to be a common interface to multiple underlying hashers.

`PasswordChecker#check` will iterate over all given hashers asking each to verify
the given password. If none of them succeeds then it returns `False`.

Note, that `PasswordChecker#make` will use only the first item from 
the `hashers` list to encode a plain password.

This class also provides `requries_update` property which indicates
that the hashed password needs to be updated (eg. algorithm has changed).


```python
from starlette.passwords import (
    InsecurePasswordHasher, PBKDF2PasswordHasher, PasswordChecker
)
hashers = [InsecurePasswordHasher(), PBKDF2PasswordHasher()]
checker = PasswordChecker(hashers)

await checker.make('password_to_hash')
await checker.check('plain_password', 'hashed_password')

print(checker.requires_update) # True if password needs to be rehashed
```

## Included hashers

### InsecurePasswordHasher

This class does not encode the password and returns it "as is".

### PBKDF2PasswordHasher

PBKDF2 password hashing algorithm.
Does not have any dependencies. 

### BCryptPasswordHasher

Uses bcrypt algorithm as a hashing backend. 
Requires `bcrypt` library to be installed.

### Argon2PasswordHasher

Uses argon2 algorithm as a hashing backend. 
Requires `argon2` library to be installed.


## Custom password hasher

When you need to make your own password hasher 
then create a new class and implement `starlette.passwords.PasswordHasher` interface:

```python
from typing import Any
from starlette.passwords import PasswordHasher

class MyPasswordHasher(PasswordHasher):
    async def make(self, password: str, salt: str = None, **kwargs: Any) -> str:
        ...
    
    async def check(self, password: str, encoded: str) -> bool:
        ...
```
