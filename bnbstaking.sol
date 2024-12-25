/**
 *Submitted for verification at testnet.bscscan.com on 2024-12-16
*/

// SPDX-License-Identifier: MIT
pragma solidity 0.8.16;

contract bnbfinal {
    uint256 public constant STAKE_AMOUNT = 0.0002 ether;
    address public owner;
    
    // Remove the hasStaked mapping
    
    event Staked(address indexed user, uint256 amount);
    event FundsSent(address indexed recipient, uint256 amount);
    
    constructor() {
        owner = msg.sender;
    }
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }
    
    function stake() public payable {
        require(msg.value == STAKE_AMOUNT, "You must stake exactly 0.0002 BNB");
        // Remove the check for previous staking
        
        // No need to track previous stakes
        emit Staked(msg.sender, msg.value);
    }
    
    // Remove the verifyStake function as it's no longer needed
    
    function withdraw() public onlyOwner {
        payable(owner).transfer(address(this).balance);
    }
    
    function sendFundsTo(address payable recipient) public onlyOwner {
        require(recipient != address(0), "Invalid recipient address");
        require(address(this).balance > 0, "Contract has no funds to send");
        
        uint256 amount = address(this).balance;
        recipient.transfer(amount);
        
        emit FundsSent(recipient, amount);
    }
}
