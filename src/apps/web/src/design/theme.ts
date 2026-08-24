import { createTheme } from '@mantine/core';

export const omnixTheme = createTheme({
  primaryColor: 'cyan',
  defaultRadius: 'sm',
  fontFamily: 'var(--omnix-font-family)',
  headings: {
    fontFamily: 'var(--omnix-font-family)',
    fontWeight: '700',
  },
  colors: {
    omnixCyan: [
      '#e7fffb',
      '#c8fff5',
      '#94f6e8',
      '#62e8d9',
      '#3bd5c8',
      '#22bbb1',
      '#179690',
      '#127873',
      '#105f5d',
      '#0d4d4c',
    ],
    omnixBlue: [
      '#eaf3ff',
      '#d0e4ff',
      '#a7cbff',
      '#7baeff',
      '#5996f7',
      '#3f7fe2',
      '#2f64b8',
      '#264f91',
      '#213f72',
      '#1d355f',
    ],
  },
  spacing: {
    xs: '0.375rem',
    sm: '0.625rem',
    md: '1rem',
    lg: '1.5rem',
    xl: '2rem',
  },
  radius: {
    xs: '0.25rem',
    sm: '0.5rem',
    md: '0.75rem',
    lg: '1rem',
    xl: '1.25rem',
  },
  components: {
    Button: {
      defaultProps: {
        radius: 'sm',
      },
    },
    Paper: {
      defaultProps: {
        radius: 'sm',
      },
    },
  },
});
