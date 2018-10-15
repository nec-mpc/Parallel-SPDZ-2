// (C) 2018 University of Bristol. See License.txt


#ifndef _Processor
#define _Processor

/* This is a representation of a processing element
 *   Consisting of 256 clear and 256 shared registers
 */

#include "Math/Share.h"
#include "Math/gf2n.h"
#include "Math/gfp.h"
#include "Math/Integer.h"
#include "Exceptions/Exceptions.h"
#include "Networking/Player.h"
#include "Auth/MAC_Check.h"
#include "Data_Files.h"
#include "Input.h"
#include "PrivateOutput.h"
#include "Machine.h"
#include "ExternalClients.h"
#include "Binary_File_IO.h"
#include "Instruction.h"

#include <stack>

class ProcessorBase
{
  // Stack
  stack<long> stacki;

protected:
  // Optional argument to tape
  int arg;

public:
  void pushi(long x) { stacki.push(x); }
  void popi(long& x) { x = stacki.top(); stacki.pop(); }

  int get_arg() const
    {
      return arg;
    }

  void set_arg(int new_arg)
    {
      arg=new_arg;
    }
};

//*****************************************************************************************//
typedef struct
{
	u_int64_t handle;
	// may hold other data
} MPC_CTX;

typedef struct __share_t {
	u_int8_t * data;
	size_t size, count, batch_size, md_ring_size;

	__share_t()
	: data(NULL),  size(0), count(0), batch_size(0), md_ring_size(0)
	{}

	void clear()
	{
		if(NULL != data) { delete data; data = NULL; }
		size = count = batch_size = md_ring_size = 0;
	}
}share_t;

typedef share_t clear_t;

class spdz_ext_ifc
{
public:
	spdz_ext_ifc();
	~spdz_ext_ifc();

	void * ext_lib_handle;

	int (*ext_init)(MPC_CTX *ctx, const int party_id, const int num_of_parties,
					const char * field, const int open_count, const int mult_count,
					const int bits_count, const int batch_size);
    int (*ext_term)(MPC_CTX *ctx);

    int (*ext_skew_bit_decomp)(MPC_CTX * ctx, const share_t * rings_in, share_t * bits_out);
    int (*ext_skew_ring_comp)(MPC_CTX * ctx, const share_t * bits_in, share_t * rings_out);
    int (*ext_input_party)(MPC_CTX * ctx, int sharing_party_id, clear_t * rings_in, share_t * rings_out);
    int (*ext_input_share)(MPC_CTX * ctx, clear_t * rings_in, share_t *rings_out);
    int (*ext_make_input_from_integer)(MPC_CTX * ctx, uint64_t * integers, int integers_count, clear_t * rings_out);
    int (*ext_make_input_from_fixed)(MPC_CTX * ctx, const char * fix_strs[], int fix_count, clear_t * rings_out);
    int (*ext_start_open)(MPC_CTX * ctx, const share_t * rings_in, clear_t * rings_out);
    int (*ext_stop_open)(MPC_CTX * ctx);
    int (*ext_make_integer_output)(MPC_CTX * ctx, const share_t * rings_in, uint64_t * integers, int * integers_count);
    int (*ext_make_fixed_output)(MPC_CTX * ctx, const share_t * rings_in, char * fix_strs[], int * fixed_count);
    int (*ext_verify_optional_suggest)(MPC_CTX * ctx, int * error);
    int (*ext_verify_final)(MPC_CTX * ctx, int * error);
    int (*ext_start_mult)(MPC_CTX * ctx, const share_t * factor1, const share_t * factor2, share_t * product);
    int (*ext_stop_mult)(MPC_CTX * ctx);

    static int load_extension_method(const char * method_name, void ** proc_addr, void * libhandle);
};

//*****************************************************************************************//

class Processor : public ProcessorBase
{
  vector<gf2n>  C2;
  vector<gfp>   Cp;
  vector<Share<gf2n> > S2;
  vector<Share<gfp> >  Sp;
  vector<long> Ci;

  // This is the vector of partially opened values and shares we need to store
  // as the Open commands are split in two
  vector<gf2n> PO2;
  vector<gfp>  POp;
  vector<Share<gf2n> > Sh_PO2;
  vector<Share<gfp> >  Sh_POp;

  vector<Share<gfp> > lhs_factors_ring;
  vector<Share<gfp> > rhs_factors_ring;

  vector<Share<gf2n> > lhs_factors_bit;
  vector<Share<gf2n> > rhs_factors_bit;

  int reg_max2,reg_maxp,reg_maxi;
  int thread_num;

  // Data structure used for reading/writing data to/from a socket (i.e. an external party to SPDZ)
  octetStream socket_stream;

  #ifdef DEBUG
    vector<int> rw2;
    vector<int> rwp;
    vector<int> rwi;
  #endif

  template <class T>
  vector< Share<T> >& get_S();
  template <class T>
  vector<T>& get_C();

  template <class T>
  vector< Share<T> >& get_Sh_PO();
  template <class T>
  vector<T>& get_PO();

  public:
  Data_Files& DataF;
  Player& P;
  MAC_Check<gf2n>& MC2;
  MAC_Check<gfp>& MCp;
  Machine& machine;

  string private_input_filename;

  Input<gf2n> input2;
  Input<gfp> inputp;
  
  PrivateOutput<gf2n> privateOutput2;
  PrivateOutput<gfp>  privateOutputp;

  ifstream public_input;
  ifstream private_input;
  ofstream public_output;
  ofstream private_output;

  unsigned int PC;
  TempVars temp;
  PRNG prng;

  int sent, rounds;

  ExternalClients external_clients;
  Binary_File_IO binary_file_io;
  
  static const int reg_bytes = 4;
  
  void reset(const Program& program,int arg); // Reset the state of the processor
  string get_filename(const char* basename, bool use_number);

  Processor(int thread_num,Data_Files& DataF,Player& P,
          MAC_Check<gf2n>& MC2,MAC_Check<gfp>& MCp,Machine& machine,
          const Program& program);
  ~Processor();

  int get_thread_num()
    {
      return thread_num;
    }

  #ifdef DEBUG  
    const gf2n& read_C2(int i) const
      { if (rw2[i]==0)
	  { throw Processor_Error("Invalid read on clear register"); }
        return C2.at(i);
      }
    const Share<gf2n> & read_S2(int i) const
      { if (rw2[i+reg_max2]==0)
          { throw Processor_Error("Invalid read on shared register"); }
        return S2.at(i);
      }
    gf2n& get_C2_ref(int i)
      { rw2[i]=1;
        return C2.at(i);
      }
    Share<gf2n> & get_S2_ref(int i)
      { rw2[i+reg_max2]=1;
        return S2.at(i);
      }
    void write_C2(int i,const gf2n& x)
      { rw2[i]=1;
        C2.at(i)=x;
      }
    void write_S2(int i,const Share<gf2n> & x)
      { rw2[i+reg_max2]=1;
        S2.at(i)=x;
      }

    const gfp& read_Cp(int i) const
      { if (rwp[i]==0)
	  { throw Processor_Error("Invalid read on clear register"); }
        return Cp.at(i);
      }
    const Share<gfp> & read_Sp(int i) const
      { if (rwp[i+reg_maxp]==0)
          { throw Processor_Error("Invalid read on shared register"); }
        return Sp.at(i);
      }
    gfp& get_Cp_ref(int i)
      { rwp[i]=1;
        return Cp.at(i);
      }
    Share<gfp> & get_Sp_ref(int i)
      { rwp[i+reg_maxp]=1;
        return Sp.at(i);
      }
    void write_Cp(int i,const gfp& x)
      { rwp[i]=1;
        Cp.at(i)=x;
      }
    void write_Sp(int i,const Share<gfp> & x)
      { rwp[i+reg_maxp]=1;
        Sp.at(i)=x;
      }

    const long& read_Ci(int i) const
      { if (rwi[i]==0)
          { throw Processor_Error("Invalid read on integer register"); }
        return Ci.at(i);
      }
    long& get_Ci_ref(int i)
      { rwi[i]=1;
        return Ci.at(i);
      }
    void write_Ci(int i,const long& x)
      { rwi[i]=1;
        Ci.at(i)=x;
      }
 #else
    const gf2n& read_C2(int i) const
      { return C2[i]; }
    const Share<gf2n> & read_S2(int i) const
      { return S2[i]; }
    gf2n& get_C2_ref(int i)
      { return C2[i]; }
    Share<gf2n> & get_S2_ref(int i)
      { return S2[i]; }
    void write_C2(int i,const gf2n& x)
      { C2[i]=x; }
    void write_S2(int i,const Share<gf2n> & x)
      { S2[i]=x; }
  
    const gfp& read_Cp(int i) const
      { return Cp[i]; }
    const Share<gfp> & read_Sp(int i) const
      { return Sp[i]; }
    gfp& get_Cp_ref(int i)
      { return Cp[i]; }
    Share<gfp> & get_Sp_ref(int i)
      { return Sp[i]; }
    void write_Cp(int i,const gfp& x)
      { Cp[i]=x; }
    void write_Sp(int i,const Share<gfp> & x)
      { Sp[i]=x; }

    const long& read_Ci(int i) const
      { return Ci[i]; }
    long& get_Ci_ref(int i)
      { return Ci[i]; }
    void write_Ci(int i,const long& x)
      { Ci[i]=x; }
  #endif

  // Template-based access
  template<class T> Share<T>& get_S_ref(int i);
  template<class T> T& get_C_ref(int i);

  // Access to external client sockets for reading clear/shared data
  void read_socket_ints(int client_id, const vector<int>& registers);
  // Setup client public key
  void read_client_public_key(int client_id, const vector<int>& registers);
  void init_secure_socket(int client_id, const vector<int>& registers);
  void init_secure_socket_internal(int client_id, const vector<int>& registers);
  void resp_secure_socket(int client_id, const vector<int>& registers);
  void resp_secure_socket_internal(int client_id, const vector<int>& registers);
  
  void write_socket(const RegType reg_type, const SecrecyType secrecy_type, const bool send_macs,
                             int socket_id, int message_type, const vector<int>& registers);

  template <class T>
  void read_socket_vector(int client_id, const vector<int>& registers);
  template <class T>
  void read_socket_private(int client_id, const vector<int>& registers, bool send_macs);

  // Read and write secret numeric data to file (name hardcoded at present)
  template <class T>
  void read_shares_from_file(int start_file_pos, int end_file_pos_register, const vector<int>& data_registers);
  template <class T>
  void write_shares_to_file(const vector<int>& data_registers);
  
  // Access to PO (via calls to POpen start/stop)
  template <class T>
  void POpen_Start(const vector<int>& reg,const Player& P,MAC_Check<T>& MC,int size);

  template <class T>
  void POpen_Stop(const vector<int>& reg,const Player& P,MAC_Check<T>& MC,int size);

  template <class T>
  void prep_shares(const vector<int>& reg, vector< Share<T> >& shares, int size);

  template <class T>
  void load_shares(const vector<int>& reg, const vector< Share<T> >& shares, int size);
#if defined(EXT_NEC_RING)
  template <class T>
  void load_bshares(const vector<int>& reg, const vector< Share<T> >& shares, int size);
#endif

  template <class T>
  void load_clears(const vector<int>& reg, vector<T>& PO, vector<T>& C, int size);

  void Ext_Skew_Bit_Decomp_R2B(const Share<gfp>& src, const vector<int>& reg, int size); //ring to bool
  void Ext_Skew_Bit_Decomp_B2B(const Share<gf2n>& src, const vector<int>& reg, int size); //bool to bool
  void Ext_Skew_Bit_Decomp_B2R(const Share<gf2n>& src, const vector<int>& reg, int size); //bool to ring
  void Ext_Skew_Ring_Comp(const int& dest, const vector<int>& reg, int size);
  void Ext_Input_Share_Int(const vector<int>& reg, int size, const int input_party_id);
  void Ext_Input_Share_Fix(const vector<int>& reg, int size, const int input_party_id);
  void Ext_Input_Clear_Int(const vector<int>& reg, int size, const int input_party_id);
  void Ext_Input_Clear_Fix(const vector<int>& reg, int size, const int input_party_id);
  void Ext_Suggest_Optional_Verification();
  void Ext_Final_Verification();
  void Ext_Mult_Start(const vector<int>& reg, int size);
  void Ext_Mult_Stop(const vector<int>& reg, int size);
  void Ext_Open_Start(const vector<int>& reg, int size);
  void Ext_Open_Stop(const vector<int>& reg, int size);

#if defined(EXT_NEC_RING)
  void Ext_BInput_Share_Int(const vector<int>& reg, int size, const int input_party_id);
  void Ext_BOpen_Start(const vector<int>& reg, int size);
  void Ext_BOpen_Stop(const vector<int>& reg, int size);
  void Ext_BMult_Start(const vector<int>& reg, int size);
  void Ext_BMult_Stop(const vector<int>& reg, int size);
#endif

  size_t mult_allocated;
  share_t mult_factor1, mult_factor2, mult_product;
  void mult_allocate(const size_t required_count);
  void mult_clear();

#if defined(EXT_NEC_RING)
  size_t bmult_allocated;
  share_t bmult_factor1, bmult_factor2, bmult_product;
  void bmult_allocate(const size_t required_count);
  void bmult_clear();
#endif

  size_t open_allocated;
  share_t open_shares;
  clear_t open_clears;
  void open_allocate(const size_t required_count);
  void open_clear();

#if defined(EXT_NEC_RING)
  size_t bopen_allocated;
  share_t bopen_shares;
  clear_t bopen_clears;
  void bopen_allocate(const size_t required_cound);
  void bopen_clear();
#endif

  // Print the processor state
  friend ostream& operator<<(ostream& s,const Processor& P);

  private:
    void maybe_decrypt_sequence(int client_id);
    void maybe_encrypt_sequence(int client_id);

    MPC_CTX spdz_gfp_ext_context;
    MPC_CTX spdz_gf2n_ext_context;
    size_t zp_word64_size;
    FILE * input_file_int, * input_file_fix, * input_file_share, *input_file_bit;
    static size_t get_zp_word64_size();
    void export_shares(const vector< Share<gfp> > & shares_in, share_t & shares_out);
    void import_shares(const share_t & shares_in, vector< Share<gfp> > & shares_out);
    void import_clears(const clear_t & clear_in, vector< gfp > & clears_out);
#if defined(EXT_NEC_RING)
    void export_shares(const vector< Share<gf2n> > & shares_in, share_t & shares_out);
    void import_shares(const share_t & shares_in, vector< Share<gf2n> > & shares_out);
    void import_clears(const clear_t & clear_in, vector< gf2n > & clears_out);
#endif
    int open_input_file();
    int close_input_file();
    int read_input_line(FILE * input_file, std::string & line);
    void mult_stop_prep_products(const vector<int>& reg, int size);


};

template<> inline Share<gf2n>& Processor::get_S_ref(int i) { return get_S2_ref(i); }
template<> inline gf2n& Processor::get_C_ref(int i)        { return get_C2_ref(i); }
template<> inline Share<gfp>& Processor::get_S_ref(int i)  { return get_Sp_ref(i); }
template<> inline gfp& Processor::get_C_ref(int i)         { return get_Cp_ref(i); }

template<> inline vector< Share<gf2n> >& Processor::get_S()       { return S2; }
template<> inline vector< Share<gfp> >& Processor::get_S()        { return Sp; }

template<> inline vector<gf2n>& Processor::get_C()                { return C2; }
template<> inline vector<gfp>& Processor::get_C()                 { return Cp; }

template<> inline vector< Share<gf2n> >& Processor::get_Sh_PO()   { return Sh_PO2; }
template<> inline vector<gf2n>& Processor::get_PO()               { return PO2; }
template<> inline vector< Share<gfp> >& Processor::get_Sh_PO()    { return Sh_POp; }
template<> inline vector<gfp>& Processor::get_PO()                { return POp; }

#endif

