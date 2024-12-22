/**
 *Submitted for verification at testnet.bscscan.com on 2024-11-29
*/

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract bnbstaking {
    uint256 public constant STAKE_AMOUNT = 0.0002 ether;
    address public owner;

    mapping(address => bool) public hasStaked;

    event Staked(address indexed user, uint256 amount);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    function stake() public payable {
        require(msg.value == STAKE_AMOUNT, "You must stake exactly 0.0002 BNB");
        require(!hasStaked[msg.sender], "You have already staked");

        hasStaked[msg.sender] = true;
        emit Staked(msg.sender, msg.value);
    }

    function verifyStake(address user) public view returns (bool) {
        return hasStaked[user];
    }

    function withdraw() public onlyOwner {
        payable(owner).transfer(address(this).balance);
    }
}