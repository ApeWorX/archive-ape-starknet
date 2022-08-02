# @version 0.3.3

event NumberChange:
    prevNum: uint256
    newNum: indexed(uint256)

owner: public(address)
myNumber: public(uint256)
prevNumber: public(uint256)

@external
def __init__():
    self.owner = msg.sender

@external
def setNumber(num: uint256):
    assert msg.sender == self.owner, "!authorized"
    assert num != 5
    self.prevNumber = self.myNumber
    self.myNumber = num
    log NumberChange(self.prevNumber, num)
