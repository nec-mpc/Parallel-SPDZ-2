// (C) 2018 University of Bristol. See License.txt

#ifndef _gf2n
#define _gf2n

#include <stdlib.h>
#include <string.h>

#include <iostream>
using namespace std;

#include "Tools/random.h"

#include "Math/gf2nlong.h"
#include "Math/field_types.h"


/* This interface compatible with the gfp interface
 * which then allows us to template the Share
 * data type.
 */


/* 
  Arithmetic in Gf_{2^n} with n<64
*/

class gf2n_short
{
//#if defined(EXT_NEC_RING)
//	SPDZEXT_VALTYPE a;
//#else

  // original (start)
  //  word a;
  // original (end)

  // added (start)
	word a;
#if defined(EXT_NEC_RING)
//	int sz = static_cast<int>(ceil(BATCH_SIZE / sizeof(SPDZEXT_VALTYPE)));
//	SPDZEXT_VALTYPE a_bit[static_cast<int>(ceil(BATCH_SIZE / sizeof(SPDZEXT_VALTYPE)))];
	int sz = static_cast<int>(ceil((float)BATCH_SIZE/(8*sizeof(SPDZEXT_VALTYPE))));
	SPDZEXT_VALTYPE a_bit[static_cast<int>(ceil((float)BATCH_SIZE/(8*sizeof(SPDZEXT_VALTYPE))))];
#endif
  // added (end)
//#endif

//	uint8_t a;

  static int n,t1,t2,t3,nterms;
  static int l0,l1,l2,l3;
  static word mask;
  static bool useC;
  static bool rewind;

  /* Assign x[0..2*nwords] to a and reduce it...  */
  void reduce_trinomial(word xh,word xl);
  void reduce_pentanomial(word xh,word xl);

  void reduce(word xh,word xl)
   { if (nterms==3)
        { reduce_pentanomial(xh,xl); }
     else
        { reduce_trinomial(xh,xl);   }
   }

  static void init_tables();

  public:

  typedef gf2n_short value_type;
  typedef word internal_type;

  static void init_field(int nn);
  static int degree() { return n; }
  static int default_degree() { return 40; }
  static int get_nterms() { return nterms; }
  static int get_t(int i) 
    { if (i==0)      { return t1; }
      else if (i==1) { return t2; }
      else if (i==2) { return t3; }
      return -1;
    }

  static DataFieldType field_type() { return DATA_GF2N; }
  static char type_char() { return '2'; }
  static string type_string() { return "gf2n"; }

  static int size() { return sizeof(a); }
  static int t()    { return 0; }

  static int default_length() { return 40; }

  word get() const {
#if defined(EXT_NEC_RING)
	  return a_bit[0];
#else
	  return a;
#endif
  }

#if defined(EXT_NEC_RING)
  SPDZEXT_VALTYPE get(int i) const { return a_bit[i]; }
#endif
  word get_word() const { return a; }

  void assign(const gf2n_short& g)     { a=g.a; }

  void assign_zero()             {
#if defined(EXT_NEC_RING)
//    for (int i=0; i<sz; i++) a_bit[i] = 0;
    memset(a_bit, 0, sizeof(SPDZEXT_VALTYPE)*sz);
#endif
      // original (start)
	  // a=0;
	  // original (end)
  }
#if defined(EXT_NEC_RING)
  void assign_zero(int i)            {
	  a_bit[i] = 0;
  }
#endif

  void assign_one()              {
#if defined(EXT_NEC_RING)
	 int modulus = 8*sizeof(SPDZEXT_VALTYPE);
    for (int i=0; i<BATCH_SIZE; i++) {
    	a_bit[i/modulus] ^= (1 << i%modulus); // little endian
    }
#endif
      // original (start)
	  // a=1;
	  // original (end)
  }
  void assign_x()                { a=2; }
  void assign(word aa)           {
#if defined(EXT_NEC_RING)
	  assign_zero();
	  int modulus = 8*sizeof(SPDZEXT_VALTYPE);
	  for (int i=0; i<BATCH_SIZE; i++) {
		  a_bit[i/modulus] ^= (static_cast<SPDZEXT_VALTYPE>(aa) << (i%modulus)); // little endian
	  }
	  // original (start)
      // a=aa;
	  // original (end)
#else
	  a=aa&mask;
#endif
  }

  void assign(long aa)           {
#if defined(EXT_NEC_RING)
	  assign_zero();
	  int modulus = 8*sizeof(SPDZEXT_VALTYPE);
	  for (int i=0; i<BATCH_SIZE; i++) {
		  a_bit[i/modulus] ^= (static_cast<SPDZEXT_VALTYPE>(aa) << (i%modulus)); // little endian
	  }
	  // original (start)
      // a=aa;
	  // original (end)
#else
	  assign(word(aa));
#endif
  }
  void assign(int aa)            {
#if defined(EXT_NEC_RING)
	  assign_zero();
	  int modulus = 8*sizeof(SPDZEXT_VALTYPE);
	  for (int i=0; i<BATCH_SIZE; i++) {
		  a_bit[i/modulus] ^= (static_cast<SPDZEXT_VALTYPE>(aa) << (i%modulus)); // little endian
	  } // original (start)
//	  a=static_cast<unsigned int>(aa);
	  // original (end)
#else
	  a=static_cast<unsigned int>(aa)&mask;
#endif
  }

#if defined(EXT_NEC_RING)
  void assign_one_elem(SPDZEXT_VALTYPE aa, int i) {
	  a_bit[i] = aa;
  }
  void assign(word aa, int i)	{
	  assign_zero(i);
//	  cout << "[gf2n.h] assign (word)" << endl;
	  int modulus = 8*sizeof(SPDZEXT_VALTYPE);
	  a_bit[i/modulus] ^= (static_cast<SPDZEXT_VALTYPE>(aa) << (i%modulus));
  }
  void assign(long aa, int i)	{
	  assign_zero(i);
//	  cout << "[gf2n.h] assign (long)" << endl;
	  int modulus = 8*sizeof(SPDZEXT_VALTYPE);
	  a_bit[i/modulus] ^= (static_cast<SPDZEXT_VALTYPE>(aa) << (i%modulus));
  }
  void assign(int aa, int i)	{
	  assign_zero(i);
//	  cout << "[gf2n.h] assign (int)" << endl;
	  int modulus = 8*sizeof(SPDZEXT_VALTYPE);
	  a_bit[i/modulus] ^= (static_cast<SPDZEXT_VALTYPE>(aa) << (i%modulus));
  }
  int get_bit(int i, int j) const
      { return (a_bit[i]>>j)&1; }
#endif

  void assign(const char* buffer) { a = *(word*)buffer; }

  int get_bit(int i) const
    { return (a>>i)&1; }
  void set_bit(int i,unsigned int b)
  { if (b==1)
      { a |= (1UL<<i); }
    else
      { a &= ~(1UL<<i); }
  }
  
  gf2n_short()              { a=0; }
  gf2n_short(word a)		{ assign(a); }
  gf2n_short(long a)		{ assign(a); }
  gf2n_short(int a)			{ assign(a); }
  gf2n_short(const char* a) { assign(a); }
  ~gf2n_short()             { ; }

  gf2n_short& operator=(const gf2n_short& g)
    {
#if defined(EXT_NEC_RING)
	  for (int i=0; i<sz; i++) a_bit[i] = g.a_bit[i];
#endif
	  // original (start)
     // assign(g);
      // original (end)
	  return *this;
    }

  int is_zero() const            { return (a==0); }
  int is_one()  const            { return (a==1); }
  int equal(const gf2n_short& y) const { return (a==y.a); }
  bool operator==(const gf2n_short& y) const { return a==y.a; }
  bool operator!=(const gf2n_short& y) const { return a!=y.a; }

  // x+y
  void add(const gf2n_short& x,const gf2n_short& y)
    {
	  a=x.a^y.a;
#if defined(EXT_NEC_RING)
	  for (int i=0; i<sz; i++) a_bit[i] = x.a_bit[i] ^ y.a_bit[i];
#endif
    }
  void add(const gf2n_short& x)
    {
	  a^=x.a;
#if defined(EXT_NEC_RING)
	  for (int i=0; i<sz; i++) a_bit[i] ^= x.a_bit[i];
#endif
    }
  template<int T>
  void add(octet* x)
    { a^=*(word*)(x); }
  template <int T>
  void add(octetStream& os)
    { add<T>(os.consume(size())); }
  void add(octet* x)
    { add<0>(x); }
  void sub(const gf2n_short& x,const gf2n_short& y)
    {
	  a=x.a^y.a;
#if defined(EXT_NEC_RING)
	  for (int i=0; i<sz; i++) a_bit[i] = x.a_bit[i] ^ y.a_bit[i];
#endif
    }
  void sub(const gf2n_short& x)
    {
	  a^=x.a;
#if defined(EXT_NEC_RING)
	  for (int i=0; i<sz; i++) a_bit[i] ^= x.a_bit[i];
#endif
    }
  // = x * y
  void mul(const gf2n_short& x,const gf2n_short& y);
  void mul(const gf2n_short& x) { mul(*this,x); }
  // x * y when one of x,y is a bit
  void mul_by_bit(const gf2n_short& x, const gf2n_short& y)   {
	  a = x.a * y.a;
#if defined(EXT_NEC_RING)
//	  for (int i=0; i<sz; i++) a_bit[i] = x.a_bit[i] * y.a_bit[i];
	  for (int i=0; i<sz; i++) a_bit[i] = x.a_bit[i] & y.a_bit[i]; // for batched computation
#endif
  }

  gf2n_short operator+(const gf2n_short& x) { gf2n_short res; res.add(*this, x); return res; }
  gf2n_short operator*(const gf2n_short& x) { gf2n_short res; res.mul(*this, x); return res; }
  gf2n_short& operator+=(const gf2n_short& x) { add(x); return *this; }
  gf2n_short& operator*=(const gf2n_short& x) { mul(x); return *this; }
  gf2n_short operator-(const gf2n_short& x) { gf2n_short res; res.add(*this, x); return res; }
  gf2n_short& operator-=(const gf2n_short& x) { sub(x); return *this; }

  void square(); 
  void square(const gf2n_short& aa);
  void invert();
  void invert(const gf2n_short& aa)
    { *this=aa; invert(); }
  void negate() { return; }
  void power(long i);

  /* Bitwise Ops */
  void AND(const gf2n_short& x,const gf2n_short& y) { a=x.a&y.a; }
  void XOR(const gf2n_short& x,const gf2n_short& y) { a=x.a^y.a; }
  void OR(const gf2n_short& x,const gf2n_short& y)  { a=x.a|y.a; }
  void NOT(const gf2n_short& x)               { a=(~x.a)&mask; }
  void SHL(const gf2n_short& x,int n)         { a=(x.a<<n)&mask; }
  void SHR(const gf2n_short& x,int n)         { a=x.a>>n; }

  gf2n_short operator&(const gf2n_short& x) { gf2n_short res; res.AND(*this, x); return res; }
  gf2n_short operator^(const gf2n_short& x) { gf2n_short res; res.XOR(*this, x); return res; }
  gf2n_short operator|(const gf2n_short& x) { gf2n_short res; res.OR(*this, x); return res; }
  gf2n_short operator!() { gf2n_short res; res.NOT(*this); return res; }
  gf2n_short operator<<(int i) { gf2n_short res; res.SHL(*this, i); return res; }
  gf2n_short operator>>(int i) { gf2n_short res; res.SHR(*this, i); return res; }

  /* Crap RNG */
  void randomize(PRNG& G);
  // compatibility with gfp
  void almost_randomize(PRNG& G)        { randomize(G); }

  void output(ostream& s,bool human) const;
  void input(istream& s,bool human);

  friend ostream& operator<<(ostream& s,const gf2n_short& x) {
//	  s << hex << showbase << x.a << dec;

	  int modulus = 8*sizeof(SPDZEXT_VALTYPE);
	  for (int i=0; i<BATCH_SIZE; i++) {
		  int obit = (x.a_bit[i/modulus] >> (i%modulus)) & 0x1;
		  s << hex << showbase << obit << dec << " ";
	  }
	  s << "\n";
	  return s;
  }

  friend istream& operator>>(istream& s,gf2n_short& x)
    { s >> hex >> x.a >> dec;
      return s;
    }


  // Pack and unpack in native format
  //   i.e. Dont care about conversion to human readable form
  void pack(octetStream& o) const
    { o.append((octet*) &a,sizeof(word)); }
  void unpack(octetStream& o)
    { o.consume((octet*) &a,sizeof(word)); }
};

#ifdef USE_GF2N_LONG
typedef gf2n_long gf2n;
#else
typedef gf2n_short gf2n;
#endif

#endif
