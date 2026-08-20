use soroban_sdk::{contracttype, Address, Env, Vec};

#[derive(Clone)]
#[contracttype]
pub struct Config {
    pub admin: Address,
    // Any Stellar asset contract on this list can be locked as collateral,
    // e.g. USDC, EURC, MGUSD. All approved tokens are treated as 1:1
    // USD-pegged — there is no per-token price feed (see
    // `pricing::collateral_ratio_bps` and the "known simplifications"
    // section of `contract/README.md`).
    pub approved_collateral_tokens: Vec<Address>,
    pub price_pusher: Address,
    pub min_collateral_ratio_bps: u32,
    pub liquidation_threshold_bps: u32,
    pub xau_usd_price: i128, // scaled by SCALAR (10^7)
}

impl Config {
    pub fn is_approved_collateral(&self, token: &Address) -> bool {
        self.approved_collateral_tokens.iter().any(|t| t == *token)
    }
}

#[derive(Clone)]
#[contracttype]
pub struct Position {
    pub collateral: i128, // amount of collateral token locked
    pub debt_xau: i128,   // amount of sXAU minted against it
}

#[derive(Clone)]
#[contracttype]
enum DataKey {
    Config,
    Position(Address),
}

pub fn get_config(env: &Env) -> Option<Config> {
    env.storage().instance().get(&DataKey::Config)
}

pub fn set_config(env: &Env, config: &Config) {
    env.storage().instance().set(&DataKey::Config, config);
}

pub fn get_position(env: &Env, user: &Address) -> Option<Position> {
    let key = DataKey::Position(user.clone());
    env.storage().persistent().get(&key)
}

pub fn set_position(env: &Env, user: &Address, position: &Position) {
    let key = DataKey::Position(user.clone());
    env.storage().persistent().set(&key, position);
    // Extend TTL on every write so active positions don't unexpectedly
    // expire — this is exactly the pattern Soroban Health (our sibling
    // project) flags when it's missing.
    env.storage().persistent().extend_ttl(&key, 100, 500);
}

pub fn clear_position(env: &Env, user: &Address) {
    let key = DataKey::Position(user.clone());
    env.storage().persistent().remove(&key);
}
