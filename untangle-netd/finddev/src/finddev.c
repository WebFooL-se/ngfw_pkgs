/**
 * $Id: outdev.c,v 1.00 2013/02/14 10:59:31 dmorris Exp $
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <pthread.h>
#include <net/if.h>
#include <net/if_arp.h>
#include <netinet/in.h>
#include <netinet/ip.h>
#include <netinet/if_ether.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <linux/sockios.h> 
#include <linux/netfilter.h> 
#include <linux/if_packet.h>
#include <libnetfilter_queue/libnetfilter_queue.h>

/**
 * Socket used for ARP queries
 */
int arp_socket = 0;

/**
 * Socket used for sending packets
 */
int pkt_socket = 0;

/**
 * Verbosity level
 */
int verbosity = 0;

/**
 * The NFqueue # to listen for packets
 */
#define QUEUE_NUM  1979

/**
 * Maximum number of interfaces in Untangle
 */
#define MAX_INTERFACES 256

/**
 * Kernel constant
 */
#define SIOCFINDEV 0x890E

/**
 * Kernel constant
 */
#define BRCTL_GET_DEVNAME 19

/**
 * length of MAC address string
 */
#define MAC_STRING_LENGTH    20

/**
 * The bypass mark
 */
#define MARK_BYPASS 0x01000000

/**
 * The device names of the interfaces (according to Untangle)
 * Example: interfacesName[0] = "eth0" interafceNames[1] = "eth1"
 */
char* interfaceNames[MAX_INTERFACES];

/**
 * The interface IDs of the interfaces (according to Untangle, not the O/S!)
 * Example: interfacesName[0] = "0" interafceNames[1] = "1"
 */
int   interfaceIds[MAX_INTERFACES];

/**
 * A global static string used to return inet_ntoa strings
 */
char inet_ntoa_name[INET_ADDRSTRLEN];

/**
 * This is the delay times for ARP requests (in microsecs)
 * 0 means give-up.
 */
unsigned long delay_array[] = {
    3 * 1000,
    6 * 1000,
    20 * 1000,
    60 * 1000,
    100 * 1000,
    1000 * 1000, /* 1 sec */
    3 * 1000 * 1000, /* 1 sec */
    0
};

/**
 * Global queue handle
 */
struct nfq_q_handle *qh = NULL;

/**
 * New thread attributes
 */
pthread_attr_t attr;

/**
 * print lock
 */
pthread_mutex_t print_mutex;

/**
 * broadcast MAC address
 */
struct ether_addr broadcast_mac = { .ether_addr_octet = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF } };

static int    _usage( char *name );
static int    _parse_args( int argc, char** argv );
static int    _debug( int level, char *lpszFmt, ...);
static char*  _inet_ntoa ( in_addr_t addr );
static void   _mac_to_string ( char *mac_string, int len, struct ether_addr* mac );
static void   _print_pkt ( struct nfq_data *tb );

static void*  _pthread_callback ( void* nfav );
static int    _nfqueue_callback ( struct nfq_q_handle *qh, struct nfgenmsg *nfmsg, struct nfq_data *nfa, void *data );

static int    _find_outdev_index ( struct nfq_data *tb );
static int    _find_next_hop ( char* dev_name, struct in_addr* dst_ip, struct in_addr* next_hop );
static int    _find_bridge_port ( struct ether_addr* mac_address, char* bridge_name );

static int    _arp_address ( struct in_addr* dst_ip, struct ether_addr* mac, char* intf_name );
static int    _arp_lookup_cache_entry ( struct in_addr* ip, char* intf_name, struct ether_addr* mac );
static int    _arp_issue_request ( struct in_addr* src_ip, struct in_addr* dst_ip, char* intf_name );
static int    _arp_fake_connect ( struct in_addr* src_ip, struct in_addr* dst_ip, char* intf_name );
static int    _arp_build_packet ( struct ether_arp* pkt, struct in_addr* src_ip, struct in_addr* dst_ip, char* intf_name );

/**
 * TODO - test with valgrind
 * TODO - handling of non-IP packets?
 * TODO - handling of IPv6?
 * TODO - SIGINT handler
 * TODO - remove logic from UVM
 */

int main ( int argc, char **argv )
{
    struct nfq_handle *h;
    struct nfnl_handle *nh;
    int fd;
    int rv;
    char buf[4096];
    
    if ( _parse_args( argc, argv ) < 0 )
        return _usage( argv[0] );

    if ( (rv = pthread_attr_init(&attr)) != 0 ) {
        fprintf( stderr, "pthread_attr_init: %s\n", strerror(rv) );
    }
    
    if ( (rv = pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED)) != 0 ) {
        fprintf( stderr, "pthread_attr_setdetachstate: %s\n", strerror(rv) );
    }

    if ( (rv = pthread_mutex_init( &print_mutex, NULL )) != 0 ) {
        fprintf( stderr, "pthread_mutex_init: %s\n", strerror(rv) );
    }

    _debug( 2, "Initializing arp socket...\n");
    if (( arp_socket = socket( PF_INET, SOCK_DGRAM, 0 )) < 0 ) {
        fprintf( stderr, "socket: %s\n", strerror(errno) );
        return -1;
    }

    _debug( 2, "Initializing pkt socket...\n");
    if (( pkt_socket = socket( PF_PACKET, SOCK_DGRAM, 0 )) < 0 ) {
        fprintf( stderr, "socket: %s\n", strerror(errno) );
        return -1;
    }

    _debug( 2, "Opening netfilter queue...\n");
    h = nfq_open();
    if (!h) {
        fprintf( stderr, "error during nfq_open()\n");
        exit(1);
    }

    _debug( 2, "Unbinding existing nf_queue handler for AF_INET (if any)\n");
    if (nfq_unbind_pf(h, AF_INET) < 0) {
        fprintf( stderr, "error during nfq_unbind_pf()\n");
        exit(1);
    }

    _debug( 2, "Binding nfnetlink_queue as nf_queue handler for AF_INET\n");
    if (nfq_bind_pf(h, AF_INET) < 0) {
        fprintf( stderr, "error during nfq_bind_pf()\n");
        exit(1);
    }

    _debug( 2, "Binding this socket to queue %i\n", QUEUE_NUM);
    qh = nfq_create_queue(h, QUEUE_NUM, &_nfqueue_callback, NULL);
    if (!qh) {
        fprintf( stderr, "error during nfq_create_queue()\n");
        exit(1);
    }

    // IPv6? FIXME: sizeof(struct iphdr) is IPv4 header
    _debug( 2, "Setting copy_packet mode\n");
    // if (nfq_set_mode(qh, NFQNL_COPY_META, 0xffff) < 0) {
    if (nfq_set_mode(qh, NFQNL_COPY_PACKET, sizeof(struct iphdr)) < 0) {
        fprintf( stderr, "can't set packet_copy mode\n");
        exit(1);
    }

    nh = nfq_nfnlh(h);
    fd = nfnl_fd(nh);

    _debug(1, "Listening for packets...\n");
    
    while ((rv = recv(fd, buf, sizeof(buf), 0)) && rv >= 0) {
        nfq_handle_packet(h, buf, rv);
    }

    _debug( 2, "Unbinding from queue 0\n");
    nfq_destroy_queue(qh);

    _debug( 2, "Closing library handle\n");
    nfq_close(h);

    _debug(1,"Exitting...");

    exit(0);
}

static int   _debug ( int level, char *lpszFmt, ... )
{
    if (verbosity >= level)
    {
        va_list argptr;

        va_start(argptr, lpszFmt);

        if ( pthread_mutex_lock( &print_mutex ) < 0 ) {
            fprintf( stderr, "pthread_mutex_lock: %s\n", strerror(errno) );
        }
        
        if ( 1 ) {
            struct timeval tv;
            struct tm tm;
            
            gettimeofday(&tv,NULL);
            if (!localtime_r(&tv.tv_sec,&tm))
                fprintf( stderr, "gmtime_r: %s\n", strerror(errno) );
            
            fprintf( stdout, "%02i-%02i %02i:%02i:%02i.%06li| ", tm.tm_mon+1,tm.tm_mday,tm.tm_hour,tm.tm_min,tm.tm_sec, (long)tv.tv_usec );
        }
          
        vfprintf( stdout, lpszFmt, argptr );

        va_end( argptr );

        fflush( stdout );

        if ( pthread_mutex_unlock( &print_mutex ) < 0 ) {
            fprintf( stderr, "pthread_mutex_unlock: %s\n", strerror(errno) );
        }
        
    }

	return 0;
}

static int   _usage ( char *name )
{
    fprintf( stderr, "Usage: %s\n", name );
    fprintf( stderr, "\t-i interface_name:index.  specify interface. Example -i eth0:1. Can be specified many times.\n" );
    fprintf( stderr, "\t-v                        increase verbosity\n" );
    return -1;
}

static int   _parse_args ( int argc, char** argv )
{
    int c = 0;

    bzero( interfaceNames, sizeof(interfaceNames));
    bzero( interfaceIds, sizeof(interfaceIds));

    while (( c = getopt( argc, argv, "i:v" ))  != -1 ) {
        switch( c ) {

        case 'v':
        {
            verbosity++;
            break;
        }

        case 'i':
        {
            /**
             * Parse name:index
             */
            char* name = NULL;
            int id = -1;

            char* token;
            int i;
            for ( i = 0 ; ((token = strsep(&optarg, ":")) != NULL ) ; i++ ) {
                if ( i == 0 )
                    name = token;
                if ( i == 1) {
                    id = atoi( token );
                }
            }

            if ( name == NULL ) {
                fprintf( stderr, "Invalid interface name\n");
                return -1;
            }
            if ( id == -1 ) {
                fprintf( stderr, "Invalid interface index\n");
                return -1;
            }
            
            /**
             * find first unused array entry and set it
             */
            for ( i = 0 ; i < MAX_INTERFACES ; i++ ) {
                if ( interfaceNames[i] == NULL ) {
                    interfaceNames[i] = strdup(name);
                    interfaceIds[i] = id;
                    _debug( 1, "Marking Interface %s with mark %i\n", interfaceNames[i], interfaceIds[i]);
                    break;
                }
            }
            
            break;
        }

        case '?':
            return -1;
        }
    }
    
    return 0;
}

static int   _nfqueue_callback (struct nfq_q_handle *qh, struct nfgenmsg *nfmsg, struct nfq_data *nfa, void *data)
{
    pthread_t id;
    int ret = pthread_create( &id, &attr, _pthread_callback, nfa );

    if (ret != 0) {
        fprintf( stderr, "pthread_create: %s\n", strerror(ret));
    }

    return 0;
}

static void* _pthread_callback ( void* nfav )
{
    struct nfq_data* nfa = (struct nfq_data*) nfav;
    int id = 0;
    struct nfqnl_msg_packet_hdr *ph;

    ph = nfq_get_msg_packet_hdr(nfa);
    if (!ph) {
        fprintf( stderr,"Packet missing header!\n" );
        return;
    }
    id = ntohl(ph->packet_id);

    if (verbosity >= 1) _print_pkt(nfa);
    
    int out_port_utindex = _find_outdev_index(nfa);

    u_int mark = nfq_get_nfmark(nfa);

    if (out_port_utindex <= 0) {
        /**
         * Unable to determine out interface
         * Set the bypass mark and accept the packet
         */
        _debug( 2, "CURRENT MARK: 0x%08x\n", mark);
        mark = mark | MARK_BYPASS;
        _debug( 2, "NEW     MARK: 0x%08x\n", mark);

        mark = htonl( mark );
        nfq_set_verdict_mark(qh, id, NF_ACCEPT, mark, 0, NULL);
        return NULL;
    }
    else {
        _debug( 2, "CURRENT MARK: 0x%08x\n", mark);
        mark = mark & 0xFFFF00FF;
        mark = mark | (out_port_utindex << 8);
        _debug( 2, "NEW     MARK: 0x%08x\n", mark);

        mark = htonl( mark );

        // NF_REPEAT instead of NF_ACCEPT to repeat mark-dst-intf
        // this will force it to save the dst mark to the connmark
        nfq_set_verdict_mark(qh, id, NF_REPEAT, mark, 0, NULL);
        return NULL;
    }
}

static void  _print_pkt ( struct nfq_data *tb )
{
    int id = 0;
    struct nfqnl_msg_packet_hdr *ph;
    u_int32_t mark,ifindex;
    int ret;
    char *data;
    char intf_name[IF_NAMESIZE];

    if ( pthread_mutex_lock( &print_mutex ) < 0 ) {
        fprintf( stderr, "pthread_mutex_lock: %s\n", strerror(errno) );
    }

    if ( 1 ) {
        struct timeval tv;
        struct tm tm;
            
        gettimeofday(&tv,NULL);
        if (!localtime_r(&tv.tv_sec,&tm))
            fprintf( stderr, "gmtime_r: %s\n", strerror(errno) );
            
        printf( "%02i-%02i %02i:%02i:%02i.%06li| ", tm.tm_mon+1,tm.tm_mday,tm.tm_hour,tm.tm_min,tm.tm_sec, (long)tv.tv_usec );
    }
    
    ph = nfq_get_msg_packet_hdr(tb);
    if (ph){
        id = ntohl(ph->packet_id);
        printf("PACKET[%i]: ", id);
        printf("hw_protocol=0x%04x hook=%u id=%u ",
               ntohs(ph->hw_protocol), ph->hook, id);
    }

    mark = nfq_get_nfmark(tb);
    if (mark)
        printf("mark=0x%08x ", mark);

    ifindex = nfq_get_indev(tb);
    if (ifindex) {
        if ( if_indextoname(ifindex, intf_name) == NULL) {
            fprintf( stderr,"if_indextoname: %s\n", strerror(errno) );
        } else {
            printf("indev=(%i,%s) ", ifindex, intf_name);
        }
    }

    ifindex = nfq_get_outdev(tb);
    if (ifindex) {
        if ( if_indextoname(ifindex, intf_name) == NULL) {
            fprintf( stderr,"if_indextoname: %s\n", strerror(errno) );
        } else {
            printf("outdev=(%i,%s) ", ifindex, intf_name);
        }
    }

    ret = nfq_get_payload(tb, &data);
    if (ret >= 0)
        printf("payload_len=%d ", ret);

    if (ret < sizeof(struct iphdr)) {
        printf("\n");
    } else {
    
        struct iphdr * ip = (struct iphdr *) data;
        struct in_addr ipa;

        printf( "IPv%i ", ip->version);

        if (ip->version != 4) {
            printf("\n");
        } else {
            printf( "src: %s ", _inet_ntoa(ip->saddr));
            printf( "dst: %s ", _inet_ntoa(ip->daddr));
            printf( "\n" );
        }
    }

    if ( pthread_mutex_unlock( &print_mutex ) < 0 ) {
        fprintf( stderr, "pthread_mutex_unlock: %s\n", strerror(errno) );
    }

    return;
}

static int   _find_outdev_index ( struct nfq_data* nfq_data )
{
    struct ether_addr mac_address;
    struct in_addr next_hop;
    char *data;
    char intf_name[IF_NAMESIZE];
    int ret = 1;
    struct nfqnl_msg_packet_hdr* ph = nfq_get_msg_packet_hdr(nfq_data);
    int packet_id = 0;

    if ( ph )
        packet_id = ntohl(ph->packet_id);

    /**
     * Lookup interface information - will return an interface like br.eth0
     */
    int ifindex = nfq_get_outdev( nfq_data );
    if (ifindex <= 0) {
        fprintf( stderr, "Unable to locate ifindex: %s\n", strerror(errno) );
        return -1;
    }
    if ( if_indextoname( ifindex, intf_name ) == NULL) {
        fprintf( stderr,"if_indextoname: %s\n", strerror(errno));
        return -1;
    }
    _debug( 2, "ARP: outdev=(%i,%s)\n", ifindex, intf_name);

    /**
     * Lookup dst IP
     */
    if ( ( ret = nfq_get_payload( nfq_data, &data ) ) < sizeof(struct iphdr) ) {
        fprintf( stderr,"packet too short: %i\n", ret);
        return -1;
    }
    struct iphdr * ip = (struct iphdr *) data;
    if ( ip->version != 4 ) {
        fprintf( stderr,"Ignoring non-IPV4 %i\n", ip->version);
        return -1;
    }
    struct in_addr dst;
    memcpy( &dst.s_addr, &ip->daddr, sizeof(in_addr_t));
    if ( _find_next_hop( intf_name, &dst, &next_hop) < 0 ) {
        fprintf( stderr, "_find_next_hop: %s\n", strerror(errno));
        return -1;
    }

    /**
     * Lookup the MAC address for next hop
     */
    if (( ret = _arp_address( &next_hop, &mac_address, intf_name )) < 0 ) {
        fprintf( stderr, "_arp_address: %s\n", strerror(errno) );
        return -1;
    }
    if ( ret == 0 ) {
        fprintf( stderr, "ARP: Unable to resolve the MAC address %s\n", inet_ntoa( next_hop ));
        return 0;
    }
    if ( memcmp(&mac_address, &broadcast_mac, sizeof(broadcast_mac)) == 0 )  {
        return 0;    
    }
    
    /**
     * Find the bridge port for next hop's MAC addr
     */
    int out_port_ifindex = _find_bridge_port( &mac_address, intf_name );
    if ( out_port_ifindex < 0 ) {
        fprintf( stderr, "_find_bridge_port: %s\n", strerror(errno) );
        return -1;
    }
    char bridge_port_intf_name[IF_NAMESIZE];
    if ( if_indextoname( out_port_ifindex, bridge_port_intf_name ) == NULL) {
        fprintf( stderr,"if_indextoname: %s\n", strerror(errno));
        return -1;
    }

    /**
     * Now find Untangle's ID for that bridge port and return that ID
     */
    int i = 0;
    for( i = 0 ; i < MAX_INTERFACES ; i++ ) {
        if (interfaceNames[i] == NULL) {
            fprintf( stderr, "Unable to find interface: %s\n", bridge_port_intf_name );
            return -1;
        }

        if ( strncmp( bridge_port_intf_name, interfaceNames[i], IF_NAMESIZE ) == 0 ) {
            if (verbosity >= 1) {
                char mac_string[MAC_STRING_LENGTH];
                _mac_to_string( mac_string, sizeof( mac_string ), &mac_address );
                _debug( 1, "RESULT[%i]: nextHop: %s nextHopMAC: %s -> systemDev: %s interfaceId: %i\n", packet_id, inet_ntoa( next_hop ), mac_string, bridge_port_intf_name, interfaceIds[i]);
            }
            return interfaceIds[i];
        }
    }
    
    return -1;
}

static char* _inet_ntoa ( in_addr_t addr )
{
    struct in_addr i;
    memset(&i, 0, sizeof(i));
    i.s_addr = addr;
    
    strncpy( inet_ntoa_name, inet_ntoa( i ), INET_ADDRSTRLEN );
    
    return inet_ntoa_name;
}

static void  _mac_to_string ( char *mac_string, int len, struct ether_addr* mac )
{
    snprintf( mac_string, len, "%02x:%02x:%02x:%02x:%02x:%02x",
              mac->ether_addr_octet[0], mac->ether_addr_octet[1], mac->ether_addr_octet[2], 
              mac->ether_addr_octet[3], mac->ether_addr_octet[4], mac->ether_addr_octet[5] );
}

/**
 * This queries the kernel for the next hop for packets destined to the specied dst_ip.
 * For example,
 */
static int   _find_next_hop ( char* dev_name, struct in_addr* dst_ip, struct in_addr* next_hop )
{
    int ifindex;
    struct 
    {
        in_addr_t addr;
        in_addr_t nh;
        char name[IFNAMSIZ];
    } args;
    
    bzero( &args, sizeof( args ));
    args.addr = dst_ip->s_addr;
    strncpy( args.name, dev_name, IFNAMSIZ);
    
    if (( ifindex = ioctl( arp_socket, SIOCFINDEV, &args )) < 0) {
        switch ( errno ) {
        case ENETUNREACH:
            fprintf( stderr, "ARP: Destination IP is not reachable: %s\n", _inet_ntoa( args.addr) );
            return 0;
        default:  /* Ignore all other error codes */
            break;
        }

        fprintf( stderr, "SIOCFINDEV[%s] %s.\n", _inet_ntoa( dst_ip->s_addr ), strerror(errno) );
        return -1;
    }

    /* If the next hop is on the local network, (eg. the next hop is the destination), 
     * the ioctl returns 0 */
    if ( args.nh != 0x00000000 ) {
        next_hop->s_addr = args.nh;
    } else {
        next_hop->s_addr = dst_ip->s_addr;
    }
    
    /* Assuming that the return value is the index of the interface,
     * make sure this is always true */
    _debug( 2, "ARP: The destination %s ", _inet_ntoa( dst_ip->s_addr ));
    _debug( 2,"is going out [%s,%d] to %s\n", args.name, ifindex, _inet_ntoa( next_hop->s_addr ));
        
    return 0;
}

/**
 * Finds the bridge port for the given MAC address,
 * returns the OS ifindex
 * or -1 for error
 * or 0 for unknown
 */
static int   _find_bridge_port ( struct ether_addr* mac_address, char* bridge_name )
{
    struct ifreq ifr;
	int ret;
    char buffer[IF_NAMESIZE];
    char mac_string[MAC_STRING_LENGTH];
    _mac_to_string( mac_string, sizeof( mac_string ), mac_address );

    unsigned long args[4] = {BRCTL_GET_DEVNAME, (unsigned long)&buffer, (unsigned long)mac_address, 0};
    
	strncpy( buffer, bridge_name, sizeof( buffer ));
	strncpy( ifr.ifr_name, bridge_name, sizeof( ifr.ifr_name ));
	ifr.ifr_data = (char*)&args;
        
	if (( ret = ioctl( arp_socket, SIOCDEVPRIVATE, &ifr )) < 0 ) {
        if ( errno == EINVAL ) {
            fprintf( stderr, "ARP: Invalid argument, MAC Address is found in ARP Cache but not in bridge MAC table.\n" );
            return -1;
        } else {
            fprintf( stderr, "ioctl: %s\n", strerror(errno) );
            return -1;
        }
    }
        
    _debug( 2,  "ARP[%s]: Outgoing interface index is %s,%d\n", bridge_name, buffer, ret );
    
	return ret;
}

/**
 * Tries to determine the MAC address corresponding with the provided dst_ip
 * Initially it looks up the dst IP in the local ARP cache
 * If not, found it will force an ARP request and then check the cache again.
 *
 * Returns 1 if successfully resolved MAC address.
 * Returns 0 if ARP resolution failed
 * Returns -1 on error
 */
static int   _arp_address ( struct in_addr* dst_ip, struct ether_addr* mac, char* intf_name )
{
    int c = 0;
    int ret;
    unsigned long delay;
    struct in_addr src_ip;

    while ( 1 ) {
        /* Check the cache before issuing the request */
        ret = _arp_lookup_cache_entry( dst_ip, intf_name, mac );
        if ( ret < 0 ) {
            fprintf( stderr, "_get_arp_entry: %s\n", strerror(errno) );
            return -1;
        } else if (ret == 1 ) {
            return 1;
        } else {
                _debug( 2,  "ARP: MAC not found for '%s' on '%s'. Sending ARP request.\n", _inet_ntoa( dst_ip->s_addr ), intf_name );
        }

        /* Connect and close so the kernel grabs the source address */
        if (( c == 0 ) && ( _arp_fake_connect( &src_ip, dst_ip, intf_name ) < 0 )) {
            fprintf( stderr, "_arp_fake_connect: %s \n", strerror(errno) );
            return -1;
        }

        /* Issue the arp request */
        if ( _arp_issue_request( &src_ip, dst_ip, intf_name ) < 0 ) {
            fprintf( stderr, "_arp_issue_request: %s \n", strerror(errno) );
            return -1;
        }

        delay = delay_array[c];
        if ( delay == 0 ) break;
        if ( delay < 0 ) {
            fprintf( stderr, "Invalid delay: index %d is %l\n", c, delay );
            return -1;
        }
        c++;
        
        _debug( 2,  "Waiting for the response for: %d ms\n", delay );
        usleep( delay );
    }
    
    return 0;
}

/**
 * Checks the ARP cache for the given IP living on the given interface
 * If found, copies the MAC to mac and returns 1
 * Otherwise, returns 0
 * Returns -1, if any error occurs
 */
static int   _arp_lookup_cache_entry ( struct in_addr* ip, char* intf_name, struct ether_addr* mac )
{
    struct arpreq request;
    struct sockaddr_in* sin = (struct sockaddr_in*)&request.arp_pa;
    struct ether_addr zero_mac = { .ether_addr_octet = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 } };

    bzero( &request, sizeof( request ));

    sin->sin_family = AF_INET;
    sin->sin_port  = 0;
    memcpy( &sin->sin_addr, ip, sizeof( sin->sin_addr ));

    request.arp_ha.sa_family = ARPHRD_ETHER;
    strncpy( request.arp_dev, intf_name, sizeof( request.arp_dev ));
    request.arp_flags = 0;
    
    int ret;
    
    if (( ret = ioctl( arp_socket, SIOCGARP, &request )) < 0 ) {
        /* This only fails if a socket has never been opened to this IP address.
         * Must also check that the address returned a zero MAC address */
        if ( errno == ENXIO ) {
            _debug( 2,  "ARP CACHE: MAC address for %s was not found\n", _inet_ntoa( ip->s_addr ));
            return 0;
        }

        fprintf( stderr, "ioctl: %s\n", strerror(errno));
        return -1;
    }

    /* Returning an all zero MAC address indicates that the MAC was not found */
    if ( memcmp( &request.arp_ha.sa_data, &zero_mac, sizeof( struct ether_addr )) == 0 ) {
        _debug( 2,  "ARP CACHE: Ethernet address for %s was not found\n", _inet_ntoa( ip->s_addr ));
        return 0;
    }

    memcpy( mac, &request.arp_ha.sa_data, sizeof( struct ether_addr ));

    if (verbosity >= 2) {
        char mac_string[MAC_STRING_LENGTH];
        _mac_to_string( mac_string, sizeof( mac_string ), mac );
        _debug( 2, "ARP: Cache resolved MAC[%d]: '%s' -> '%s'\n", ret, inet_ntoa( *ip ), mac_string );
    }

    return 1;
}

/**
 * This function creates a "fake" connection to the specified dst_ip
 * and resolves the source IP that would be used to connect to dst_ip.
 * It copies this value into src_ip and returns.
 *
 * Returns: 0 on success, -1 on error
 */
static int   _arp_fake_connect ( struct in_addr* src_ip, struct in_addr* dst_ip, char* intf_name )
{
    struct sockaddr_in addr;
    int fake_fd;
    int ret = 0;

    int _critical_section( void ) {
        int one = 1;
        u_int addr_len = sizeof( addr );
        int name_len = strnlen( intf_name, sizeof( intf_name )) + 1;

        if ( setsockopt( fake_fd, SOL_SOCKET, SO_BINDTODEVICE, intf_name, name_len ) < 0 ) {
            fprintf( stderr, "setsockopt(SO_BINDTODEVICE,%s): %s\n", intf_name, strerror(errno) );
        }

        if ( setsockopt( fake_fd, SOL_SOCKET, SO_BROADCAST,  &one, sizeof(one)) < 0 ) {
            fprintf( stderr, "setsockopt(SO_BROADCAST)\n" );
        }

        if ( setsockopt( fake_fd, SOL_SOCKET, SO_DONTROUTE, &one, sizeof( one )) < 0 ) {
            fprintf( stderr, "setsockopt(SO_DONTROUTE)\n" );
        }
        
        if ( connect( fake_fd, (struct sockaddr*)&addr, sizeof( addr )) < 0 ) {
            fprintf( stderr, "connect[%s] %s\n", _inet_ntoa( dst_ip->s_addr ), strerror(errno) );
            return -1;
        }
        
        if ( getsockname( fake_fd, (struct sockaddr*)&addr, &addr_len ) < 0 ) {
            fprintf( stderr, "getsockname: %s\n", strerror(errno) );
            return -1;
        }
        
        memcpy( src_ip, &addr.sin_addr, sizeof( addr.sin_addr ));
        return 0;
    }
    
    addr.sin_family = AF_INET;

    /* NULL PORT is not actually used */
    #define NULL_PORT            59999 
    addr.sin_port = htons( NULL_PORT );
    memcpy( &addr.sin_addr, dst_ip, sizeof( addr.sin_addr ));

    if (( fake_fd = socket( AF_INET, SOCK_DGRAM, 0 )) < 0 ) {
        fprintf( stderr, "socket: %s\n", strerror( errno ) );
        return -1;
    }
    
    ret = _critical_section();
    
    if ( close( fake_fd ) < 0 ) {
        fprintf( stderr, "close: %s\n", strerror( errno ) );
    }
    
    return ret;
}

/**
 * Sends an ARP request for the dst_ip (from the src_ip) on intf_name
 */
static int   _arp_issue_request ( struct in_addr* src_ip, struct in_addr* dst_ip, char* intf_name )
{
    struct ether_arp pkt;
    struct sockaddr_ll broadcast = {
        .sll_family   = AF_PACKET,
        .sll_protocol = htons( ETH_P_ARP ),
        .sll_ifindex  = 0, // set me 
        .sll_hatype   = htons( ARPHRD_ETHER ),
        .sll_pkttype  = PACKET_BROADCAST, 
        .sll_halen    = ETH_ALEN,
        .sll_addr = {
            0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
        }
    };
    int size;

    /* Set the index */
    broadcast.sll_ifindex = if_nametoindex(intf_name);

    if (broadcast.sll_ifindex == 0) {
        fprintf( stderr, "failed to find index of \"%s\"\n", intf_name);
        return -1;
    }
    
    if ( _arp_build_packet( &pkt, src_ip, dst_ip, intf_name ) < 0 ) {
        fprintf( stderr, "_arp_build_packet: %s\n", strerror(errno));
        return -1;
    }
    
    size = sendto( pkt_socket, &pkt, sizeof( pkt ), 0, (struct sockaddr*)&broadcast, sizeof( broadcast ));

    if ( size < 0 ) {
        fprintf( stderr, "sendto( %i , %08x , %i, %i, %08x, %i )\n", arp_socket, &pkt, sizeof( pkt ), 0, (struct sockaddr*)&broadcast, sizeof( broadcast ));
        fprintf( stderr, "sendto: %s\n", strerror(errno) );
        return -1;
    }
    
    if ( size != sizeof( pkt )) {
        fprintf( stderr, "Transmitted truncated ARP packet %d < %d\n", size, sizeof( pkt ));
        return -1;
    }
         
    return 0;
}

static int   _arp_build_packet ( struct ether_arp* pkt, struct in_addr* src_ip, struct in_addr* dst_ip, char* intf_name )
{
    struct ifreq ifr;
    struct ether_addr mac;
    struct sockaddr_ll broadcast = {
        .sll_family   = AF_PACKET,
        .sll_protocol = htons( ETH_P_ARP ),
        .sll_ifindex  = 6, // SETME WITH SOMETHING
        .sll_hatype   = htons( ARPHRD_ETHER ),
        .sll_pkttype  = PACKET_BROADCAST, 
        .sll_halen    = ETH_ALEN,
        .sll_addr = {
            0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
        }
    };

    strncpy( ifr.ifr_name, intf_name, IFNAMSIZ );

    if ( ioctl( arp_socket, SIOCGIFHWADDR, &ifr ) < 0 ) {
        fprintf( stderr, "ioctl: %s\n", strerror( errno ));
        return -1;
    }

    memcpy( &mac, ifr.ifr_hwaddr.sa_data, sizeof( mac ));
    
    pkt->ea_hdr.ar_hrd = htons( ARPHRD_ETHER );
    pkt->ea_hdr.ar_pro = htons( ETH_P_IP );
    pkt->ea_hdr.ar_hln = ETH_ALEN;
	pkt->ea_hdr.ar_pln = sizeof( *dst_ip );
	pkt->ea_hdr.ar_op  = htons( ARPOP_REQUEST );
    memcpy( &pkt->arp_sha, &mac, sizeof( pkt->arp_sha ));
    memcpy( &pkt->arp_spa, src_ip, sizeof( pkt->arp_spa ));
    memcpy( &pkt->arp_tha, &broadcast.sll_addr, sizeof( pkt->arp_tha ));
    memcpy( &pkt->arp_tpa, dst_ip, sizeof( pkt->arp_tpa ));

    return 0;
}