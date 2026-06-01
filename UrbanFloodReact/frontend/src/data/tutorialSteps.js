/**
 * tutorialSteps.js — Step definitions for all tutorial modes.
 *
 * Each step:
 *   target      CSS selector for the element to spotlight (null = centered modal)
 *   title       Step heading
 *   content     Description text
 *   placement   Tooltip position: 'top' | 'bottom' | 'left' | 'right'
 *   tab         (optional) auto-switch sidebar tab before this step
 *   spotlightPadding  (optional) extra px around spotlight
 */

// ─── LOGIN PAGE ──────────────────────────────────────────────────────
export const loginSteps = [
  {
    target: null,
    title: '👋 Welcome to UrbanFlood',
    content: 'This is the Digital Twin Driven Flood Evacuation System. Let\'s walk through the login page so you know how to get started.',
    placement: 'center',
  },
  {
    target: '.login-form-panel form',
    title: '🔐 Login Form',
    content: 'Enter your username and password here to sign in. If you don\'t have an account yet, you can register one.',
    placement: 'left',
    spotlightPadding: 12,
  },
  {
    target: '.login-form-panel form button[type="submit"]',
    title: '➡️ Sign In',
    content: 'Click this button to sign in with your credentials. You can also toggle between Sign In and Register modes.',
    placement: 'top',
  },
  {
    target: '.login-form-panel [style*="gridTemplateColumns"]',
    title: '🎮 Sandbox Access',
    content: 'Use these demo buttons for instant access without credentials. Each role gives you a different experience:\n\n• Authority — DRA emergency command\n• Researcher — Full simulation lab\n• Citizen — Flood navigation\n• Simulate — Test flood routing',
    placement: 'top',
    spotlightPadding: 10,
  },
  {
    target: null,
    title: '✅ You\'re Ready!',
    content: 'That\'s everything on the login page. Choose a role above to explore the app, or sign in with your account. Each mode has its own in-app tutorial you can trigger anytime!',
    placement: 'center',
  },
];

// ─── RESEARCHER MODE ─────────────────────────────────────────────────
export const researcherSteps = [
  {
    target: null,
    title: '🔬 Researcher Mode',
    content: 'Welcome to the Full Simulation Lab! This mode gives you complete control over flood simulation, evacuation algorithms, and analytics. Let\'s walk through each feature.',
    placement: 'center',
  },
  {
    target: '.sidebar',
    title: '📋 Control Sidebar',
    content: 'This sidebar is your main control panel. It contains region selection, simulation parameters, and all configuration options.',
    placement: 'right',
    spotlightPadding: 0,
  },
  {
    target: '.sidebar-tabs',
    title: '🗂️ Navigation Tabs',
    content: 'Switch between different panels here:\n• Simulation — Set up and run floods\n• Evacuation — View results after simulation\n• Experts — AI advisory panel\n• Sentinel — Weather automation',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '#tutorial-region-selector',
    title: '📍 Region Selector',
    content: 'Select a region using the District → Taluk → Hobli hierarchy. This loads the road network, shelters, and population data for that area.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '#tutorial-population-panel',
    title: '👥 Population Panel',
    content: 'View the population count for the loaded region. This determines how many people will be simulated during the flood.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '#tutorial-shelters-panel',
    title: '🏥 Shelters Panel',
    content: 'Lists all available safe shelters in the region — hospitals, schools, community halls. Each has a capacity limit.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '#tutorial-rainfall-panel',
    title: '🌧️ Rainfall Configuration',
    content: 'Set the rainfall intensity (in mm). Higher values create more severe flooding. You can also fetch real historical rainfall data.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '.evac-mode-toggle',
    title: '🚶 Evacuation Mode',
    content: 'Toggle this to scale the population to 1% for faster, focused evacuation route analysis.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '.optim-panel',
    title: '⚡ Algorithm Selection',
    content: 'Choose which optimization algorithm to use:\n• GA — Genetic Algorithm\n• ACO — Ant Colony Optimization\n• PSO — Particle Swarm Optimization\n• All — Compare all three simultaneously',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '#tutorial-sim-controls',
    title: '▶️ Simulation Controls',
    content: 'Configure simulation steps and decay factor, then click Run to start the flood simulation. You can pause and reset at any time.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '.map-container',
    title: '🗺️ Interactive Map',
    content: 'The main map shows the road network, flood zones (red/orange), shelters (green markers), and evacuation routes after simulation.',
    placement: 'left',
  },
  {
    target: '.sidebar-tab.evac-tab',
    title: '📊 Evacuation Results',
    content: 'After running a simulation, this tab shows detailed evacuation analysis: shelter assignments, algorithm comparison, and shelter gap analysis.',
    placement: 'right',
  },
  {
    target: '.sidebar-tab:nth-child(3)',
    title: '🤖 AI Experts Panel',
    content: 'This tab has AI-powered expert advisors: Logistics Chief, Tactical Commander, Civic Authority, and Mass SOS. They analyze your simulation results and generate downloadable reports.',
    placement: 'right',
  },
  {
    target: '.sidebar-tab:nth-child(4)',
    title: '🌧️ Weather Sentinel',
    content: 'The automation panel monitors real-time weather data and can auto-trigger simulations when rainfall exceeds your set threshold.',
    placement: 'right',
  },
  {
    target: '#tutorial-lang-toggle',
    title: '🌐 Language Toggle',
    content: 'Switch between English and Kannada at any time. The entire interface supports bilingual operation.',
    placement: 'bottom',
  },
  {
    target: null,
    title: '🎉 Tutorial Complete!',
    content: 'You\'re all set! Start by selecting a region, configuring rainfall, and running your first simulation. The evacuation analysis will appear automatically after the simulation completes.',
    placement: 'center',
  },
];

// ─── AUTHORITY (DRA) MODE ────────────────────────────────────────────
export const authoritySteps = [
  {
    target: null,
    title: '🏢 Authority (DRA) Mode',
    content: 'Welcome to the Disaster Response Authority command center. This streamlined interface is designed for emergency situations — faster setup, automatic best-algorithm selection, and Mass SOS capabilities.',
    placement: 'center',
  },
  {
    target: '.sidebar',
    title: '🎛️ DRA Command Panel',
    content: 'The DRA sidebar is simplified for rapid response. It auto-loads population and shelter data, and uses ACO + Live Traffic by default.',
    placement: 'right',
    tab: 'setup',
    spotlightPadding: 0,
  },
  {
    target: '#tutorial-dra-hobli-select',
    title: '📍 Quick Region Select',
    content: 'Select any hobli from the dropdown. In DRA mode, all data (population, shelters, elevation) loads automatically — no manual steps needed.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '#tutorial-dra-pin-drop',
    title: '📌 Pin-Drop Mode',
    content: 'Click anywhere on the map to drop a pin. The system will automatically identify the hobli at that location and prepare it for simulation.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '#tutorial-dra-rainfall',
    title: '🌧️ Rainfall Intensity',
    content: 'Set the rainfall level for the simulation. In emergencies, use real-time data or set it to match current conditions.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '#tutorial-dra-run-btn',
    title: '🚀 Run Evacuation',
    content: 'One click runs the full pipeline: flood simulation → ACO optimization with live traffic → evacuation routes. No algorithm selection needed — the system picks the best automatically.',
    placement: 'right',
    tab: 'setup',
  },
  {
    target: '.sidebar-tabs',
    title: '🗂️ Result Tabs',
    content: 'After simulation: Evacuation tab shows routes and shelter assignments, Experts tab provides AI analysis, and Sentinel monitors weather.',
    placement: 'right',
  },
  {
    target: '.map-container',
    title: '🗺️ Real-Time Map',
    content: 'The map shows flood zones, evacuation routes, shelter locations, bus routes, and metro lines — all updated in real-time during simulation.',
    placement: 'left',
  },
  {
    target: null,
    title: '✅ Ready for Action!',
    content: 'Select a region and hit Run Evacuation to start. The system handles algorithm selection, traffic data, and shelter assignment automatically. Use the Experts tab for AI-powered situational analysis.',
    placement: 'center',
  },
];

// ─── CITIZEN MODE ────────────────────────────────────────────────────
export const citizenSteps = [
  {
    target: null,
    title: '🧑 Citizen Navigation Mode',
    content: 'This mode helps you navigate to safety during a flood. It detects your location, finds the safest route, and provides turn-by-turn directions.',
    placement: 'center',
  },
  {
    target: '.floating-glass-header',
    title: '📍 Header',
    content: 'The header shows you\'re in Flood Navigation mode. You can log out from here anytime.',
    placement: 'bottom',
  },
  {
    target: '.citizen-bottom-sheet',
    title: '📱 Bottom Sheet',
    content: 'This panel shows your current options. When your location is detected, you\'ll see buttons to search for a destination or find the nearest safe shelter.',
    placement: 'top',
    spotlightPadding: 8,
  },
  {
    target: null,
    title: '🗺️ Finding Your Route',
    content: 'You can either:\n• Search for a specific destination\n• Tap a point on the map\n• Let the system find the nearest safe shelter automatically\n\nThe system calculates flood-aware routes that avoid dangerous areas.',
    placement: 'center',
  },
  {
    target: null,
    title: '🧭 Turn-by-Turn Navigation',
    content: 'Once a route is found, you\'ll see:\n• Distance and ETA at the top\n• Flood depth warnings\n• Step-by-step walking/driving directions\n• Live rerouting if conditions change',
    placement: 'center',
  },
  {
    target: null,
    title: '✅ Stay Safe!',
    content: 'The system will guide you to the nearest safe shelter. If all routes are flooded, you\'ll see emergency contact information (call 112). Your route updates automatically as flood conditions change.',
    placement: 'center',
  },
];

// ─── SIMULATE MODE ───────────────────────────────────────────────────
export const simulateSteps = [
  {
    target: null,
    title: '⚡ Simulation Sandbox',
    content: 'This mode lets you test flood evacuation scenarios. Pick start and end points, configure conditions, and watch the simulation play out in real-time.',
    placement: 'center',
  },
  {
    target: '#tutorial-sim-header',
    title: '🎯 Simulation Header',
    content: 'The header identifies you\'re in the Evacuation Navigator. Use the logout button when you\'re done.',
    placement: 'bottom',
  },
  {
    target: '#tutorial-sim-map',
    title: '🗺️ Interactive Map',
    content: 'Click on the map to set your start point (A marker), then click again to set your destination (B marker). You can also drag markers to adjust positions.',
    placement: 'left',
  },
  {
    target: '#tutorial-sim-config',
    title: '⚙️ Simulation Config',
    content: 'Configure your simulation:\n• Travel mode (Car/Bike/Walk)\n• Rainfall intensity\n• Navigation mode (Simulated vs Real-time)\n• Traffic conditions',
    placement: 'left',
  },
  {
    target: null,
    title: '▶️ Running the Simulation',
    content: 'Once configured, hit Start to watch:\n• Your vehicle marker moves along the route\n• Flood zones appear and evolve\n• The system reroutes if your path gets flooded\n• Rainfall heatmap shows affected areas',
    placement: 'center',
  },
  {
    target: null,
    title: '🎬 Replay & Analysis',
    content: 'After completion, you can replay the entire journey, review rerouting events, and see detailed statistics about distance, time, and flood conditions encountered.',
    placement: 'center',
  },
  {
    target: null,
    title: '✅ Start Exploring!',
    content: 'Click on the map to place your start point, then your destination. The system will compute routes and you can begin the simulation!',
    placement: 'center',
  },
];
