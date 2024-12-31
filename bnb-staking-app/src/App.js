import React, { useState, useEffect } from 'react';
import Web3 from 'web3';

const BNBStakingApp = () => {
  const [web3, setWeb3] = useState(null);
  const [account, setAccount] = useState(null);
  const [contract, setContract] = useState(null);
  const [hasStaked, setHasStaked] = useState(false);
  const [error, setError] = useState(null);

  // Contract details
  const contractAddress = '0xA546819d48330FB2E02D3424676d13D7B8af3bB2'; // Replace with your deployed contract address
  const contractABI = [{"inputs":[],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"recipient","type":"address"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"FundsSent","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"Staked","type":"event"},{"inputs":[],"name":"STAKE_AMOUNT","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"hasStaked","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address payable","name":"recipient","type":"address"}],"name":"sendFundsTo","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"stake","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"user","type":"address"}],"name":"verifyStake","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"}]
  // Connect to MetaMask
  const connectWallet = async () => {
    if (window.ethereum) {
      try {
        // Request network change
        await window.ethereum.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: '0x61' }], // BSC Testnet Chain ID
        });
  
        // Request account access
        const accounts = await window.ethereum.request({ 
          method: 'eth_requestAccounts' 
        });
        
        // Create Web3 instance with provider
        const web3Instance = new Web3(window.ethereum);
        setWeb3(web3Instance);
        setAccount(accounts[0]);
  
        // Verify contract exists
        const contractInstance = new web3Instance.eth.Contract(
          contractABI, 
          contractAddress
        );
        
        // Test contract interaction
        try {
          // Directly hardcode the stake amount
          const stakeAmount = await web3Instance.utils.toWei('0.0002', 'ether');
          setContract(contractInstance);
          
          // Check staking status
          const stakeStatus = await contractInstance.methods
            .verifyStake(accounts[0])
            .call();
          setHasStaked(stakeStatus);
        } catch (contractError) {
          setError(`Contract Interaction Error: ${contractError.message}`);
        }
  
      } catch (error) {
        setError(`Wallet Connection Error: ${error.message}`);
      }
    } else {
      setError('MetaMask not detected. Please install MetaMask.');
    }
  };
  
  // Modify stake function
  const handleStake = async () => {
    if (!contract || !account) {
      setError('Please connect wallet first');
      return;
    }
  
    try {
      // Hardcode stake amount
      const stakeAmount = await web3.utils.toWei('0.0002', 'ether');
  
      // Send transaction to stake
      await contract.methods.stake().send({
        from: account,
        value: stakeAmount,
        gas: 300000 // Adjust gas limit as needed
      });
  
      // Update staking status
      setHasStaked(true);
      setError(null);
    } catch (error) {
      setError('Staking failed: ' + error.message);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10 p-6 border rounded-lg shadow-lg">
      <h2 className="text-2xl font-bold mb-4">BNB Staking</h2>
      
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4">
          {error}
        </div>
      )}

      {!account ? (
        <button 
          onClick={connectWallet}
          className="w-full bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
        >
          Connect Wallet
        </button>
      ) : (
        <>
          <div className="mb-4">
            <p>Connected Wallet: {account}</p>
          </div>
          
          {hasStaked ? (
            <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative">
              You have already staked
            </div>
          ) : (
            <button 
              onClick={handleStake}
              className="w-full bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded"
            >
              Stake 0.0002 BNB
            </button>
          )}
        </>
      )}
    </div>
  );
};

export default BNBStakingApp;