# Battle of Tunes

Battle of Tunes is an innovative Telegram-based music battle minigame with a "winner takes all" approach. Players stake a set amount of BNB, join a lobby with other participants, and generate music using a custom music generation model. The generated tracks are evaluated by an advanced machine learning model, and the winner claims the entire pool of staked tokens.

---

## 1. Limitations of Traditional Song Battle Approaches

- **Time-Consuming:** Determining a winner through traditional voting mechanisms is often a lengthy process.
- **Lack of Transparency:** Winners are frequently decided by subjective, biased voting without a clear set of evaluation metrics.
- **Inefficient and Costly Transactions:** Traditional centralized payment methods often involve high fees, slower transaction times, and less secure, mutable systems.

---

## 2. Our Solution

### Objective and Unbiased Evaluation

Our system utilizes a Random Forest Regressor to evaluate music submissions based on the following parameters:
- Acousticness
- Energy
- Danceability
- Liveness
- Loudness
- Instrumentalness
- Key

#### Key Benefits:
- **Elimination of Bias:** The use of an unbiased regression model ensures results are precise and evidence-based.
- **Faster Results:** The automated evaluation process is significantly quicker than traditional voting.

### Enhanced Transaction Security

A smart contract deployed on the Binance Smart Chain (BSC) Testnet ensures secure, transparent, and low-fee staking and prize distribution, offering a robust alternative to traditional systems.

---

## 3. Key Features

### Telegram Bots

Our game is managed through three specialized Telegram bots:

1. **Battle of Tunes Entry Bot**:
   - Manages user registration and staking functionality.
   - **How to Use:**
     1. Save the `stakingbot.py` file locally.
     2. Install dependencies:
        
        ```bash
        
        pip install telebot mysql-connector-python web3
        ```
     4. Run the following command:
        
        ```bash
        
        python3 stakingbot.py
        ```

2. **SubmissionHandler Bot**:
   - Oversees battles after all players have staked and entered the lobby.
   - **How to Use:**
     1. Save the `submissionhandler.py` file locally.
     2. Install dependencies:
        
        ```bash
        
        pip install telebot mysql-connector-python web3
        ```
     4. Run the following command:
        
        ```bash
        
        python3 submissionhandler.py
        ```

3. **MusicGenBot**:
   - Enables players to generate music using custom prompts.
   - **How to Use:**
     1. Save the `musicgenbot.py` file locally.
     2. Install dependencies:
        
        ```bash
        
        pip install telebot mysql-connector-python web3
        ```
     4. Run the following command:
        
        ```bash
        
        python3 musicgenbot.py
        ```

### Music Generation Model

- Built using Facebook’s music-gen model.
- **How to Use:**
  1. Open the [Musicgen Colab Notebook](https://colab.research.google.com/drive/1YsEpJCdtlmIs9XPPCJc64j5aidIZezDx?usp=sharing).
  2. **Run All Cells** to get an API endpoint to utilize the model in your **MusicGenBot**.

### Music Evaluation Model

- Employs a Random Forest Regression model to evaluate music submissions based on seven distinct metrics.
- **How to Use:**
  1. Open the [Musiceval Colab Notebook](https://colab.research.google.com/drive/1S6Ve-75riwKPrKDbW-eaT0N5zlmWPI1K?usp=sharing).
  2. **Run All Cells** to get an API endpoint to utilize the evaluation model in your **submissionHandler bot**.

### Smart Contract

- A BSC Testnet smart contract handles staking and prize distribution.

Contract address: 0xA546819d48330FB2E02D3424676d13D7B8af3bB2

View contract in block explorer : https://testnet.bscscan.com/address/0xa546819d48330fb2e02d3424676d13d7b8af3bb2

---

## 4. How to Play

### Requirements

- Use the **Telegram PC/Mac App** for the best experience (avoid Telegram Web).
- Install the **MetaMask Wallet Chrome Extension** to stake tokens.
- The game requires **exactly 3 players**.
- Each player needs **at least 0.04 tBNB** (BSC Testnet tokens) to cover staking and network fees.

### Entry Point
[Battle of Tunes Entry Bot Link](https://t.me/BattleofTunesEntry_bot)

### Game Flow

#### In Entry Bot
1. Press the **Start** button or type **/start**.
2. Stake 0.0002 tBNB using **/stake <wallet_address>**.
3. If previously staked, verify using **/verify <wallet_address>**.
4. Once verified, join the group link to enter your lobby.

#### In Staking Page
1. Press the “Connect Wallet” button and approve the connection in MetaMask.
2. Stake tokens and sign the transaction in MetaMask.

#### In Lobby
1. Wait for other players to stake and join the group.
2. After the battle starts, use **/gentrack** to get the MusicGenBot link.

#### In MusicGenBot
1. Type **/start** and verify your identity with your wallet address.
2. Type **/generate** and provide a prompt to generate music.
3. Submit or regenerate the track as needed.

Once submitted, evaluation takes **10-15 minutes**, and the winner receives the pot.



---

## License
This project is licensed under the [MIT License](https://opensource.org/licenses/MIT).

Built with ❤️ by @Marshal-AM and @SamFelix03.
