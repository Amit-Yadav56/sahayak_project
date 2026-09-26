// Sample data for testing the UI
export const INITIAL_SCHEMES = [
  {
    id: 1,
    name: "PM Kisan Samman Nidhi",
    ministry: "Ministry of Agriculture",
    category: "Agriculture",
    benefitType: "Cash Transfer",
    benefitAmount: "Rs 6,000 / year (3 installments)",
    description: "Financial assistance for farmer families who own cultivable land.",
    eligibilitySummary: "Small and marginal farmers owning agricultural land. Must have bank account and Aadhaar.",
    documentsRequired: "Aadhaar Card, Land papers (Khasra/Khatauni), Bank passbook",
    howToApply: "Register at pmkisan.gov.in or visit a CSC center.",
    applicationUrl: "https://pmkisan.gov.in",
    state: "Central",
    criteria: {
      minAge: 18,
      maxAge: 75,
      maxIncome: 300000,
      requiresLand: true,
      allowedGenders: ["all"],
      allowedCastes: ["all"]
    }
  },
  {
    id: 2,
    name: "Ayushman Bharat (PM-JAY)",
    ministry: "Ministry of Health",
    category: "Healthcare",
    benefitType: "Health Insurance",
    benefitAmount: "Up to Rs 5 Lakh coverage per family per year",
    description: "Cashless secondary and tertiary hospital treatment for low income families.",
    eligibilitySummary: "Low income households and BPL families listed under SECC criteria.",
    documentsRequired: "Ration card, Aadhaar card, PM-JAY letter or card",
    howToApply: "Check your name at beneficiary.nha.gov.in or visit any government hospital helpdesk.",
    applicationUrl: "https://beneficiary.nha.gov.in",
    state: "Central",
    criteria: {
      minAge: 0,
      maxAge: 100,
      maxIncome: 250000,
      requiresLand: false,
      allowedGenders: ["all"],
      allowedCastes: ["all"]
    }
  },
  {
    id: 3,
    name: "PM Awas Yojana (Gramin)",
    ministry: "Ministry of Rural Development",
    category: "Housing",
    benefitType: "Construction Grant",
    benefitAmount: "Rs 1.20 Lakh to Rs 1.30 Lakh",
    description: "Assistance to construct a permanent pucca house for families living in kutcha houses.",
    eligibilitySummary: "Rural families who do not currently own a pucca house anywhere in India.",
    documentsRequired: "Aadhaar, Bank details, MGNREGA job card number",
    howToApply: "Through the local Panchayat or Gram Pradhan.",
    applicationUrl: "https://pmayg.nic.in",
    state: "Central",
    criteria: {
      minAge: 21,
      maxAge: 70,
      maxIncome: 180000,
      requiresNoHouse: true,
      allowedGenders: ["all"],
      allowedCastes: ["all"]
    }
  },
  {
    id: 4,
    name: "Sukanya Samriddhi Yojana",
    ministry: "Ministry of Finance",
    category: "Women & Child",
    benefitType: "Savings Scheme",
    benefitAmount: "8.2% annual interest + tax deduction",
    description: "Small savings scheme to build education and marriage funds for young girls.",
    eligibilitySummary: "Parents or legal guardians of a girl child aged 10 years or younger.",
    documentsRequired: "Girl's birth certificate, guardian ID and address proof",
    howToApply: "Open an account at any post office branch or participating bank.",
    applicationUrl: "https://www.indiapost.gov.in",
    state: "Central",
    criteria: {
      minAge: 0,
      maxAge: 10,
      maxIncome: 9999999,
      allowedGenders: ["female"],
      allowedCastes: ["all"]
    }
  },
  {
    id: 5,
    name: "Post Matric Scholarship (SC)",
    ministry: "Ministry of Social Justice",
    category: "Education",
    benefitType: "Scholarship & Fee Waiver",
    benefitAmount: "Course fees covered + monthly maintenance allowance",
    description: "Financial support for Scheduled Caste students pursuing post-secondary education.",
    eligibilitySummary: "SC category students whose family income is below Rs 2.5 Lakh per year.",
    documentsRequired: "Caste Certificate, Income Certificate, Previous marksheet, Bank passbook",
    howToApply: "Apply online on National Scholarship Portal (scholarships.gov.in).",
    applicationUrl: "https://scholarships.gov.in",
    state: "Central",
    criteria: {
      minAge: 15,
      maxAge: 35,
      maxIncome: 250000,
      allowedGenders: ["all"],
      allowedCastes: ["SC"]
    }
  },
  {
    id: 6,
    name: "PM Mudra Loan",
    ministry: "Ministry of Finance",
    category: "Employment",
    benefitType: "Business Loan",
    benefitAmount: "Up to Rs 10 Lakh collateral-free loan",
    description: "Loans for starting or expanding small businesses and micro-enterprises.",
    eligibilitySummary: "Any Indian citizen running or starting a non-farm business.",
    documentsRequired: "ID proof, Business address proof, 6 months bank statement",
    howToApply: "Apply online at udyamimitra.in or contact your local bank branch.",
    applicationUrl: "https://www.mudra.org.in",
    state: "Central",
    criteria: {
      minAge: 18,
      maxAge: 65,
      maxIncome: 1000000,
      allowedGenders: ["all"],
      allowedCastes: ["all"]
    }
  },
  {
    id: 7,
    name: "Indira Gandhi Widow Pension",
    ministry: "Ministry of Rural Development",
    category: "Social Welfare",
    benefitType: "Monthly Pension",
    benefitAmount: "Rs 300 to Rs 1,000 / month",
    description: "Monthly pension support for widows living below the poverty line.",
    eligibilitySummary: "Widows aged 40-79 years from BPL households.",
    documentsRequired: "Husband's death certificate, Age proof, BPL card, Bank details",
    howToApply: "Submit form at the local Social Welfare Office or Block office.",
    applicationUrl: "https://nsap.nic.in",
    state: "Central",
    criteria: {
      minAge: 40,
      maxAge: 79,
      maxIncome: 100000,
      requiresWidow: true,
      allowedGenders: ["female"],
      allowedCastes: ["all"]
    }
  },
  {
    id: 8,
    name: "PM Kusum Solar Pump",
    ministry: "Ministry of Renewable Energy",
    category: "Agriculture",
    benefitType: "Subsidy",
    benefitAmount: "60% subsidy on solar pump setup",
    description: "Helps farmers install solar-powered irrigation pumps on farmland.",
    eligibilitySummary: "Farmers with cultivable land seeking replacement of diesel pumps.",
    documentsRequired: "Aadhaar card, Land papers, Bank details",
    howToApply: "Apply through state renewable energy portal or pmkusum.mnre.gov.in.",
    applicationUrl: "https://pmkusum.mnre.gov.in",
    state: "Central",
    criteria: {
      minAge: 18,
      maxAge: 75,
      maxIncome: 1500000,
      requiresLand: true,
      allowedGenders: ["all"],
      allowedCastes: ["all"]
    }
  }
];

export const CATEGORIES = [
  "All",
  "Agriculture",
  "Healthcare",
  "Housing",
  "Women & Child",
  "Education",
  "Employment",
  "Social Welfare"
];
