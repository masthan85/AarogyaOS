// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', '.expo/*'],
  },
  {
    rules: {
      // Apostrophes and quotes in <Text> render literally in React Native; escaping adds nothing.
      'react/no-unescaped-entities': 'off',
      // Existing screens set state in effects and update one ref during render. Reported as
      // warnings until each is reviewed on a device; new code should not add to them.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/refs': 'warn',
    },
  },
  {
    // Tests call jest.mock before importing, and group imports beside the cases that use them.
    files: ['**/__tests__/**'],
    rules: {
      'import/first': 'off',
      'import/no-duplicates': 'off',
    },
  },
]);
