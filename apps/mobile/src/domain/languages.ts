// Offline fallback only. The app asks the server for the organisation's languages (GET /languages);
// language support is data, not code.
export const LANGUAGE_OPTIONS: { tag: string; label: string }[] = [
  { tag: 'en-IN', label: 'English' },
  { tag: 'hi-IN', label: 'हिन्दी' },
  { tag: 'te-IN', label: 'తెలుగు' },
  { tag: 'ta-IN', label: 'தமிழ்' },
  { tag: 'kn-IN', label: 'ಕನ್ನಡ' },
  { tag: 'ml-IN', label: 'മലയാളം' },
  { tag: 'mr-IN', label: 'मराठी' },
  { tag: 'bn-IN', label: 'বাংলা' },
  { tag: 'gu-IN', label: 'ગુજરાતી' },
  { tag: 'pa-IN', label: 'ਪੰਜਾਬੀ' },
  { tag: 'ur-IN', label: 'اردو' },
  { tag: 'or-IN', label: 'ଓଡ଼ିଆ' },
  { tag: 'as-IN', label: 'অসমীয়া' },
];
